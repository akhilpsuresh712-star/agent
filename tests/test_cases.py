"""The 5 fixture scenarios. These assert the right action for the RIGHT REASON —
several check triggered_rules, not just the action, because that's where careless
implementations get the correct answer by accident.
"""

from __future__ import annotations

import pytest

from app.fixtures_loader import load_sample_requests
from app.schemas.decision import Action
from app.schemas.output import AgentRunRequest, RunStatus

CASES = {c["id"]: c for c in load_sample_requests("fixtures")}


def _run(harness, case_id):
    c = CASES[case_id]
    return harness.run(
        AgentRunRequest(message=c["message"], department=c["department"], user_id=c["user_id"])
    )


def test_case_001_low_risk_creates_draft(harness):
    r = _run(harness, "case_001_low_risk_software")
    assert r.decision.action == Action.CREATE_DRAFT_PO
    assert r.status == RunStatus.COMPLETED
    assert r.draft_po is not None
    assert r.draft_po.status == "DRAFT"          # drafted, NOT submitted
    assert r.draft_po.total_usd == 2400          # 3 x 800


def test_case_002_hardware_rule_not_amount_rule(harness):
    """EXACTLY $5000: the hardware rule fires, the amount rule must NOT."""
    r = _run(harness, "case_002_hardware_requires_approval")
    assert r.decision.action == Action.NEED_HUMAN_APPROVAL
    assert r.status == RunStatus.NEEDS_APPROVAL
    assert "policy_002" in r.decision.triggered_rules        # hardware
    assert "policy_001" not in r.decision.triggered_rules    # NOT the amount rule
    assert r.draft_po.total_usd == 5000


def test_case_003_in_budget_but_over_threshold(harness):
    """$8000 < $10000 budget, but > $5000 threshold — different axes."""
    r = _run(harness, "case_003_budget_too_high")
    assert r.decision.action == Action.NEED_HUMAN_APPROVAL
    assert "policy_001" in r.decision.triggered_rules        # amount over threshold
    assert "budget_exceeded" not in r.decision.triggered_rules  # still within budget


def test_case_004_clarification_names_missing_quantity(harness):
    """Oracle resolves via alias; what's missing is QUANTITY, not the item."""
    r = _run(harness, "case_004_missing_information")
    assert r.decision.action == Action.ASK_CLARIFICATION
    assert r.status == RunStatus.NEEDS_CLARIFICATION
    assert "quantity" in r.decision.missing_fields
    assert "item" not in r.decision.missing_fields           # Oracle IS in catalog
    assert "quantity" in r.decision.reason


def test_case_005_injection_routes_structurally(harness):
    """Injection text is irrelevant: routes to approval/reject on the deterministic path."""
    r = _run(harness, "case_005_prompt_injection")
    assert r.decision.action in (Action.NEED_HUMAN_APPROVAL, Action.REJECT)
    assert r.status in (RunStatus.NEEDS_APPROVAL, RunStatus.REJECTED)
    assert "policy_004" in r.decision.triggered_rules        # bypass detected (defense-in-depth)
    assert "policy_002" in r.decision.triggered_rules        # ...but hardware would gate it anyway
    assert r.draft_po is None                                 # rejected -> nothing to submit


@pytest.mark.parametrize("case_id", list(CASES))
def test_every_case_returns_valid_response(harness, case_id):
    """Final output always validates against AgentRunResponse (guardrail 5A)."""
    r = _run(harness, case_id)
    # Re-validate by round-tripping through the model.
    from app.schemas.output import AgentRunResponse

    AgentRunResponse.model_validate(r.model_dump())
