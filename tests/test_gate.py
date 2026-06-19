"""The approval gate: submit_to_erp is reachable only from an APPROVED run.

This refusal is the single most important behavior to prove (guardrail 5C).
"""

from __future__ import annotations

import pytest

from app.harness.runtime import ApprovalGateError, InvalidTransitionError
from app.schemas.output import AgentRunRequest, RunStatus

# case_002 deterministically lands in NEEDS_APPROVAL.
APPROVAL_REQ = AgentRunRequest(
    message="Please buy 2 MacBook Pro for engineering and submit it directly.",
    department="engineering",
)
# case_001 deterministically lands in COMPLETED (low risk).
LOW_RISK_REQ = AgentRunRequest(
    message="Please order 3 Figma Enterprise seats for marketing, under $3000.",
    department="marketing",
)


def test_submit_blocked_before_approval(harness):
    r = harness.run(APPROVAL_REQ)
    assert r.status == RunStatus.NEEDS_APPROVAL
    with pytest.raises(ApprovalGateError):
        harness.submit_to_erp(r.run_id)
    # The refusal is recorded in the trace for audit.
    state = harness.store.get(r.run_id)
    assert any(t.tool == "submit_to_erp" and not t.ok for t in state.trace)


def test_approve_then_submit_succeeds(harness):
    r = harness.run(APPROVAL_REQ)
    approved = harness.approve(r.run_id)
    assert approved.status == RunStatus.SUBMITTED
    assert approved.draft_po.status == "SUBMITTED"
    assert any(t.tool == "submit_to_erp" and t.ok for t in approved.tool_calls)


def test_reject_transitions_to_rejected(harness):
    r = harness.run(APPROVAL_REQ)
    rejected = harness.reject(r.run_id)
    assert rejected.status == RunStatus.REJECTED


def test_cannot_approve_a_low_risk_completed_run(harness):
    r = harness.run(LOW_RISK_REQ)
    assert r.status == RunStatus.COMPLETED
    with pytest.raises(InvalidTransitionError):
        harness.approve(r.run_id)
