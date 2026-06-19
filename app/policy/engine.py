"""The deterministic policy engine — no LLM, ever.

A Decision is a pure function of (category, amount, budget_remaining, bypass).
The fixture cases and their traps drive every line here:

  case_001  2400 software, in budget, < 5000        -> CREATE_DRAFT_PO
  case_002  5000 hardware (EXACTLY 5000)            -> NEED_HUMAN_APPROVAL via the
            *hardware* rule (policy_002), NOT the amount rule. 5000 is not > 5000.
  case_003  8000 software, in budget but > 5000     -> NEED_HUMAN_APPROVAL (policy_001).
            Budget and threshold are different axes.
  case_004  handled upstream (missing quantity)     -> ASK_CLARIFICATION
  case_005  250000 hardware, over budget, bypass    -> REJECT (budget hard gate);
            also flags policy_002 + policy_004. Safety is structural — the bypass
            text changes nothing about the routing.

Design decision (documented in ARCHITECTURE.md): an order that exceeds remaining
budget is a hard REJECT. A human approver in this system cannot conjure budget;
finance must raise it first. This is the deliberate answer to the
"under-threshold-but-over-budget" case that the fixtures don't cover.
"""

from __future__ import annotations

from app.fixtures_loader import PolicyConfig
from app.schemas.decision import Action, Decision, RiskLevel

# Rule ids match policies.json so reasons/traces are auditable against the fixtures.
RULE_AMOUNT = "policy_001"          # over approval threshold
RULE_HARDWARE = "policy_002"        # hardware requires approval
RULE_ENTERPRISE_SW = "policy_003"   # enterprise software requires approval
RULE_BYPASS = "policy_004"          # explicit bypass attempt must not auto-execute
RULE_BUDGET = "budget_exceeded"     # local hard gate (not a numbered fixture policy)

_CATEGORY_RULE = {
    "hardware": RULE_HARDWARE,
    "enterprise_software": RULE_ENTERPRISE_SW,
}


class PolicyEngine:
    def __init__(self, policy: PolicyConfig) -> None:
        self._policy = policy

    def decide(
        self,
        *,
        category: str,
        amount_usd: float,
        budget_remaining_usd: float,
        bypass_detected: bool,
    ) -> Decision:
        threshold = self._policy.approval_threshold_usd
        restricted = set(self._policy.restricted_categories)

        triggered: list[str] = []

        # --- collect every applicable signal (for a complete audit trail) ----
        category_rule = _CATEGORY_RULE.get(category)
        if category in restricted and category_rule:
            triggered.append(category_rule)

        # Strict > : exactly-at-threshold is NOT over threshold. This is the
        # case_002 trap — 5000 must not fire the amount rule.
        if amount_usd > threshold:
            triggered.append(RULE_AMOUNT)

        over_budget = amount_usd > budget_remaining_usd
        if over_budget:
            triggered.append(RULE_BUDGET)

        if bypass_detected:
            triggered.append(RULE_BYPASS)

        # --- decide the action by precedence ---------------------------------
        # 1. Budget is a hard constraint: can't be auto-drafted, can't be cured
        #    by human approval here -> REJECT.
        # 2. A bypass attempt must never auto-execute -> at least approval.
        # 3. Restricted category or over-threshold amount -> human approval.
        # 4. Otherwise low risk -> auto draft.
        if over_budget:
            action = Action.REJECT
            risk = RiskLevel.HIGH if bypass_detected else RiskLevel.MEDIUM
        elif bypass_detected or (category in restricted) or amount_usd > threshold:
            action = Action.NEED_HUMAN_APPROVAL
            risk = RiskLevel.HIGH if bypass_detected else RiskLevel.MEDIUM
        else:
            action = Action.CREATE_DRAFT_PO
            risk = RiskLevel.LOW

        return Decision(
            action=action,
            risk_level=risk,
            requires_human_approval=(action == Action.NEED_HUMAN_APPROVAL),
            reason=self._explain(action, triggered, amount_usd, budget_remaining_usd, threshold),
            triggered_rules=triggered,
        )

    def _explain(
        self,
        action: Action,
        triggered: list[str],
        amount: float,
        budget: float,
        threshold: float,
    ) -> str:
        descs = self._policy.rule_descriptions
        if action == Action.REJECT:
            return (
                f"Order total ${amount:,.0f} exceeds the department's remaining budget "
                f"${budget:,.0f}; rejected pending a budget adjustment."
            )
        if action == Action.CREATE_DRAFT_PO:
            return (
                f"Low risk: ${amount:,.0f} is within budget and at or below the "
                f"${threshold:,.0f} approval threshold; drafting a PO (not submitted)."
            )
        # NEED_HUMAN_APPROVAL — name the policies that fired.
        reasons = [descs.get(r, r) for r in triggered if r != RULE_BUDGET]
        joined = " ".join(reasons) if reasons else "Requires human approval."
        return f"Human approval required. {joined}"
