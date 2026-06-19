"""check_policy — thin tool wrapper over the deterministic PolicyEngine.

The tool exists so the policy evaluation shows up in the tool-call trace as a
first-class step, but it adds no logic of its own: all risk reasoning lives in
PolicyEngine.decide.
"""

from __future__ import annotations

from app.policy.engine import PolicyEngine
from app.schemas.decision import Decision
from app.schemas.tools_io import CheckPolicyInput


def check_policy(engine: PolicyEngine, inp: CheckPolicyInput) -> Decision:
    return engine.decide(
        category=inp.category,
        amount_usd=inp.amount_usd,
        budget_remaining_usd=inp.budget_remaining_usd,
        bypass_detected=inp.bypass_detected,
    )
