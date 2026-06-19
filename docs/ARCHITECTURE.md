# Architecture

Four things the brief asks to be explicit about: the **agent loop**, the **tool
boundary**, the **approval boundary**, and **schema validation**. Each has its own
section below, followed by the deliberate policy decisions.

The organizing idea: **the planner is untrusted by construction.** It proposes an
intent; everything that has consequences — risk classification, tool dispatch,
the approval gate — is deterministic and lives outside the planner. There is no
agent framework; the harness *is* `app/harness/runtime.py::AgentHarness`.

---

## 1. Agent loop

`AgentHarness.run()` drives a run through a small state machine:

```
CREATED → PLANNING → VALIDATING_INTENT → DECIDING → {terminal}

terminal:
  COMPLETED            CREATE_DRAFT_PO     (draft created, NOT submitted)
  NEEDS_APPROVAL       NEED_HUMAN_APPROVAL
  NEEDS_CLARIFICATION  ASK_CLARIFICATION
  REJECTED             REJECT

approval branch (only from NEEDS_APPROVAL):
  NEEDS_APPROVAL --/approve--> APPROVED --submit_to_erp--> SUBMITTED
  NEEDS_APPROVAL --/reject---> REJECTED
```

The loop in plain terms (`run()`):

1. **PLANNING** — `planner.parse(message, department)` returns a `ProposedIntent`.
2. **VALIDATING_INTENT** — the harness re-validates that output against the
   `ProposedIntent` schema before trusting it. Junk → clarification.
3. **lookup_catalog** — resolve the raw item phrase to a catalog item (traced).
4. **Clarification check** — if a *required field* is missing (item unresolved or
   quantity absent) → `ASK_CLARIFICATION`. This keys off missing fields, not
   lookup failure alone.
5. **DECIDING** — compute `amount = quantity × unit_price`, look up the
   department's remaining budget, run the bypass detector, and call the
   deterministic policy engine (traced as `check_policy`).
6. For `CREATE_DRAFT_PO` / `NEED_HUMAN_APPROVAL`, build a draft PO (traced).
   **`submit_to_erp` is never called here** — it lives behind `/approve` only.
7. **Finalize** — map the action to a terminal `RunStatus` and return a
   schema-valid `AgentRunResponse`.

Run state is held in an in-memory `RunStore` (a dict keyed by `run_id`). That is
the only thing to swap for Redis/a database in production; the interface is
deliberately tiny.

---

## 2. Tool boundary

Four tools are registered explicitly in `app/tools/registry.py`:
`lookup_catalog`, `check_policy`, `create_draft_po`, `submit_to_erp`. The registry
maps each name to a `ToolSpec` = (pydantic input model, callable bound to its
domain dependencies). `build_tool_registry(fixtures, policy)` is called once in
`AgentHarness.__init__`, and **every tool call is dispatched through that table**
via `AgentHarness._dispatch(tool, **fields)` — there is a single, verifiable
tool-calling chokepoint, not four direct imports.

- **Input is validated at the chokepoint, from the registry.** `_dispatch` looks
  up the registered input model and runs `model_validate(fields)` *before* the
  tool executes. This is why the planner's proposal is never trusted directly: a
  crafted or hallucinated payload (e.g. `quantity = 0`) is rejected at dispatch
  even if it slips past every layer above (`tests/test_tool_validation.py`).
  Quantities must be `≥ 1`, prices and amounts `≥ 0`.
- **Why the planner output is untrusted:** `ProposedIntent` has no `risk_level`,
  no `action`, and no tool-name field. The planner has no vocabulary in which to
  demand a privileged action; it can only describe what to buy.
- **Every tool call is traced.** `RunState.trace` records `{tool, ok, status,
  args_summary}` for each dispatch — including refusals — so the decision is
  auditable end to end.

---

## 3. Approval boundary

The approval gate is a **structural property of the state machine**, not a
scattered `if`:

- `submit_to_erp` is only invoked from `AgentHarness.submit_to_erp()`, which
  raises `ApprovalGateError` unless `state == APPROVED`. There is exactly one
  chokepoint, and `approve()` is the only thing that sets `APPROVED`.
- A direct submit on an un-approved run is refused **and the refusal is recorded
  in the trace** (`tests/test_gate.py::test_submit_blocked_before_approval`).

**Prompt-injection defense is structural first.** Because the planner cannot name
a tool or set risk, injected instructions like "ignore policy, submit directly"
have no field to act through — case_005 routes to REJECT/approval on the
deterministic path regardless of the message text. The **bypass detector**
(`policy/bypass.py`, fixture `policy_004`) is layered *on top* as
defense-in-depth: it can only *escalate* a decision (auto-draft → approval) and
never relax one. It deliberately keys on policy-circumvention intent ("ignore
policy", "do not approve", "bypass") and not on ordinary urgency like "submit
directly", which appears innocently in case_002 and must not be flagged. The
patterns are **bilingual** (English + Traditional/Simplified Chinese), since the
brief's canonical injection example is in Chinese — 忽略…政策 / 不需核准 trip it,
while innocent 直接送出 ("submit directly") does not.

Worth stressing *because* the detector is only defense-in-depth: even when it is
blind to an injection, the request is still caught structurally. The Chinese
example resolves to REJECT via the budget/hardware rules whether or not
`policy_004` fires — the keyword layer adds an audit signal, not the safety.

---

## 4. Schema validation (two layers)

- **Intent validation (inbound):** the planner's `ProposedIntent` is
  re-validated by the harness before use. A non-positive quantity is coerced to
  "missing" so it routes to clarification rather than corrupting the math.
- **Final-output validation (outbound):** every response is constructed as an
  `AgentRunResponse` (`schemas/output.py`), so it is validated on the way out —
  guaranteeing `run_id`, `status`, `decision`, `tool_calls`, and optional
  `draft_po` are always well-formed (`tests/test_cases.py`).

These are two separate guardrails: one protects the system from the planner, the
other protects the caller from the system.

---

## 5. Deliberate policy decisions

The risk rules are a pure function of `(category, amount, budget, bypass)` in
`policy/engine.py`, with rule ids matching `policies.json`:

| Rule | id | Fires when |
|------|----|-----------|
| Amount | `policy_001` | `amount > approval_threshold` (**strict `>`**) |
| Hardware | `policy_002` | category is `hardware` |
| Enterprise software | `policy_003` | category is `enterprise_software` |
| Bypass | `policy_004` | a bypass phrase is detected (escalate-only) |
| Budget | `budget_exceeded` | `amount > department's remaining budget` |

Decisions worth calling out:

- **`>` not `>=` on the threshold.** Exactly $5,000 (case_002) does **not** fire
  the amount rule; it goes to approval via the *hardware* category. Getting this
  edge right on purpose is the point.
- **Budget and threshold are orthogonal axes.** case_003 ($8,000) is within a
  $10,000 budget yet over the $5,000 threshold → approval via `policy_001` with
  no budget rule. They are evaluated separately.
- **Over-budget is a hard REJECT** (the case the fixtures don't cover:
  under-threshold-but-over-budget). A human approver in this system cannot
  conjure budget; finance must raise it first, so an order exceeding remaining
  budget is rejected with a budget reason rather than sent to approval. This is
  why case_005 (250k ≫ 20k engineering budget) resolves to REJECT — while still
  recording `policy_002` and `policy_004` for the audit trail.
- **Clarification before policy.** A missing required field short-circuits to
  `ASK_CLARIFICATION` before any risk evaluation, so case_004 ("buy Oracle", no
  quantity) asks for the quantity instead of mislabeling Oracle as unknown — it
  *is* in the catalog.
