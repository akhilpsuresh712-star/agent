"""AgentHarness — the agent loop, the tool boundary, the approval gate, the trace.

There is no off-the-shelf agent framework here: the harness *is* AgentHarness.
It owns the run state machine and is the only place tools are dispatched, so the
approval ordering rule (submit_to_erp only from an APPROVED run) is a structural
property, not an `if` a caller could forget.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from app.fixtures_loader import Fixtures
from app.planner.base import Planner
from app.policy.bypass import detect_bypass
from app.policy.engine import PolicyEngine
from app.schemas.decision import Action, Decision, RiskLevel
from app.schemas.intent import ProposedIntent
from app.schemas.output import AgentRunRequest, AgentRunResponse, RunStatus
from app.schemas.tools_io import (
    LookupCatalogOutput,
    ToolCallRecord,
)
from app.tools.registry import ToolSpec, build_tool_registry
from app.harness.state import RunState, RunStore
from app.logging_config import get_logger

log = get_logger("procurement.harness")

_ACTION_TO_STATUS = {
    Action.CREATE_DRAFT_PO: RunStatus.COMPLETED,
    Action.NEED_HUMAN_APPROVAL: RunStatus.NEEDS_APPROVAL,
    Action.ASK_CLARIFICATION: RunStatus.NEEDS_CLARIFICATION,
    Action.REJECT: RunStatus.REJECTED,
}


class HarnessError(Exception):
    """Base class for harness control-flow errors."""


class RunNotFoundError(HarnessError):
    pass


class InvalidTransitionError(HarnessError):
    pass


class ApprovalGateError(HarnessError):
    """Raised when submit_to_erp is attempted on a run that is not APPROVED."""


class AgentHarness:
    def __init__(self, *, planner: Planner, fixtures: Fixtures, store: RunStore | None = None) -> None:
        self.planner = planner
        self.fixtures = fixtures
        self.policy = PolicyEngine(fixtures.policy)
        self.store = store or RunStore()
        # The tool registry: name -> ToolSpec (input model + bound callable).
        # Every tool call is dispatched through this table (see _dispatch).
        self.tools = build_tool_registry(fixtures, self.policy)

    # --- main loop --------------------------------------------------------
    def run(self, request: AgentRunRequest) -> AgentRunResponse:
        state = self.store.create(request)
        log.info(
            "run %s START dept=%s planner=%s msg=%r",
            state.run_id, request.department, getattr(self.planner, "name", "?"), request.message,
        )

        # PLANNING — the planner proposes; it is untrusted.
        state.status = RunStatus.PLANNING
        proposed = self.planner.parse(request.message, request.department)
        log.debug("run %s planner proposed: %s", state.run_id, proposed.model_dump())

        # VALIDATING_INTENT — re-validate planner output before trusting it.
        state.status = RunStatus.VALIDATING_INTENT
        try:
            intent = ProposedIntent.model_validate(proposed.model_dump())
        except ValidationError:
            log.warning("run %s intent validation FAILED -> ASK_CLARIFICATION", state.run_id)
            decision = Decision(
                action=Action.ASK_CLARIFICATION,
                risk_level=RiskLevel.LOW,
                requires_human_approval=False,
                reason="Could not understand the request; the proposed intent failed validation.",
                missing_fields=["item", "quantity"],
            )
            return self._finalize(state, decision)
        state.intent = intent

        # lookup_catalog (traced)
        lookup = self._lookup(state, intent.item_query)

        # Clarification keys off MISSING REQUIRED FIELDS, not lookup failure alone.
        # (case_004: Oracle resolves, but quantity is missing -> clarify quantity.)
        missing: list[str] = []
        if not lookup.resolved:
            missing.append("item")
        if intent.quantity is None:
            missing.append("quantity")
        if missing:
            decision = Decision(
                action=Action.ASK_CLARIFICATION,
                risk_level=RiskLevel.LOW,
                requires_human_approval=False,
                reason=f"Need clarification: missing required field(s): {', '.join(missing)}.",
                missing_fields=missing,
            )
            return self._finalize(state, decision)

        # DECIDING — deterministic policy. Bypass detection is defense-in-depth.
        state.status = RunStatus.DECIDING
        amount = round(intent.quantity * float(lookup.unit_price_usd), 2)
        budget = self.fixtures.budget_remaining(request.department)
        bypass = detect_bypass(intent.raw_message)
        decision = self._check_policy(
            state,
            category=str(lookup.category),
            amount=amount,
            quantity=intent.quantity,
            budget=budget,
            bypass=bypass,
        )
        state.decision = decision

        # Build a draft for actionable orders (auto-draft or held-for-approval),
        # but never for REJECT. submit_to_erp is NOT called here — only via /approve.
        if decision.action in (Action.CREATE_DRAFT_PO, Action.NEED_HUMAN_APPROVAL):
            self._create_draft(state, lookup, intent)

        return self._finalize(state, decision)

    # --- approval branch --------------------------------------------------
    def approve(self, run_id: str) -> AgentRunResponse:
        state = self._require(run_id)
        if state.status != RunStatus.NEEDS_APPROVAL:
            raise InvalidTransitionError(
                f"Cannot approve run in state {state.status.value}; expected NEEDS_APPROVAL."
            )
        state.status = RunStatus.APPROVED
        log.info("run %s APPROVED by reviewer -> submitting", run_id)
        # The gate below is the single chokepoint for submit_to_erp.
        return self.submit_to_erp(run_id)

    def reject(self, run_id: str) -> AgentRunResponse:
        state = self._require(run_id)
        if state.status != RunStatus.NEEDS_APPROVAL:
            raise InvalidTransitionError(
                f"Cannot reject run in state {state.status.value}; expected NEEDS_APPROVAL."
            )
        state.status = RunStatus.REJECTED
        state.decision = Decision(
            action=Action.REJECT,
            risk_level=(state.decision.risk_level if state.decision else RiskLevel.MEDIUM),
            requires_human_approval=False,
            reason="Rejected by human reviewer.",
            triggered_rules=(state.decision.triggered_rules if state.decision else []),
        )
        log.info("run %s REJECTED by reviewer", run_id)
        return self._response(state)

    def submit_to_erp(self, run_id: str) -> AgentRunResponse:
        """THE GATE. submit_to_erp is reachable only from an APPROVED run."""
        state = self._require(run_id)
        if state.status != RunStatus.APPROVED:
            self._trace(
                state,
                ToolCallRecord(
                    tool="submit_to_erp",
                    ok=False,
                    status=f"blocked: run not approved (state={state.status.value})",
                    args_summary=f"run_id={run_id}",
                ),
            )
            raise ApprovalGateError(
                f"submit_to_erp refused: run {run_id} is {state.status.value}, not APPROVED."
            )
        if state.draft_po is None:
            raise ApprovalGateError(f"submit_to_erp refused: run {run_id} has no draft PO.")

        out = self._dispatch("submit_to_erp", draft_po=state.draft_po)
        state.draft_po = out.submitted_po
        state.status = RunStatus.SUBMITTED
        self._trace(
            state,
            ToolCallRecord(
                tool="submit_to_erp",
                ok=True,
                status=f"submitted {out.erp_reference}",
                args_summary=f"po={out.submitted_po.po_number}",
            ),
        )
        return self._response(state)

    # --- tool dispatch ----------------------------------------------------
    def _dispatch(self, tool: str, /, **fields):
        """THE tool-calling chokepoint. Look the tool up in the registry,
        validate the payload against its registered input model (guardrail 5B —
        the planner's fields are never trusted raw), then run the bound callable.
        Every tool in the system flows through here. `tool` is positional-only so
        a payload field named `name` (e.g. create_draft_po) can't collide."""
        spec: ToolSpec = self.tools[tool]
        validated = spec.input_model.model_validate(fields)
        return spec.run(validated)

    # --- traced tool calls ------------------------------------------------
    def _trace(self, state: RunState, record: ToolCallRecord) -> None:
        """Record a tool call on the run trace AND log it. Single chokepoint so
        every dispatch (including refusals) shows up identically in the API
        response trace and in stdout logs."""
        state.record(record)
        level = logging.INFO if record.ok else logging.WARNING
        log.log(level, "run %s tool %s: %s | %s",
                state.run_id, record.tool, record.status, record.args_summary)

    def _lookup(self, state: RunState, item_query: str) -> LookupCatalogOutput:
        out = self._dispatch("lookup_catalog", item_query=item_query)
        self._trace(
            state,
            ToolCallRecord(
                tool="lookup_catalog",
                ok=True,
                status="resolved" if out.resolved else "unresolved",
                args_summary=f"item_query={item_query!r}",
            ),
        )
        return out

    def _check_policy(
        self, state: RunState, *, category: str, amount: float, quantity: int, budget: float, bypass: bool
    ) -> Decision:
        decision = self._dispatch(
            "check_policy",
            category=category,
            amount_usd=amount,
            quantity=quantity,
            budget_remaining_usd=budget,
            bypass_detected=bypass,
        )
        self._trace(
            state,
            ToolCallRecord(
                tool="check_policy",
                ok=True,
                status=f"{decision.action.value} ({','.join(decision.triggered_rules) or 'no rules'})",
                args_summary=f"category={category}, amount=${amount:,.0f}, budget=${budget:,.0f}, bypass={bypass}",
            ),
        )
        return decision

    def _create_draft(self, state: RunState, lookup: LookupCatalogOutput, intent: ProposedIntent) -> None:
        draft = self._dispatch(
            "create_draft_po",
            item_id=str(lookup.item_id),
            name=str(lookup.name),
            category=str(lookup.category),
            quantity=int(intent.quantity),  # guaranteed non-None here
            unit_price_usd=float(lookup.unit_price_usd),
            department=intent.department,
        )
        state.draft_po = draft
        self._trace(
            state,
            ToolCallRecord(
                tool="create_draft_po",
                ok=True,
                status=f"draft {draft.po_number} (${draft.total_usd:,.0f})",
                args_summary=f"{draft.quantity} x {draft.name}",
            ),
        )

    # --- finalize / helpers ----------------------------------------------
    def _finalize(self, state: RunState, decision: Decision) -> AgentRunResponse:
        state.decision = decision
        state.status = _ACTION_TO_STATUS[decision.action]
        log.info(
            "run %s DECISION=%s risk=%s rules=%s -> status=%s",
            state.run_id, decision.action.value, decision.risk_level.value,
            decision.triggered_rules or [], state.status.value,
        )
        return self._response(state)

    def _response(self, state: RunState) -> AgentRunResponse:
        assert state.decision is not None
        return AgentRunResponse(
            run_id=state.run_id,
            status=state.status,
            decision=state.decision,
            tool_calls=list(state.trace),
            draft_po=state.draft_po,
        )

    def _require(self, run_id: str) -> RunState:
        state = self.store.get(run_id)
        if state is None:
            raise RunNotFoundError(f"Unknown run_id: {run_id}")
        return state
