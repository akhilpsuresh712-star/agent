"""The Decision — output of the deterministic policy engine.

Risk is never inferred by an LLM. A Decision is a pure function of
(category, amount, budget, bypass_flag) and is fully auditable via triggered_rules,
which carry the fixture policy ids (policy_001..policy_004).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Action(str, Enum):
    CREATE_DRAFT_PO = "CREATE_DRAFT_PO"
    NEED_HUMAN_APPROVAL = "NEED_HUMAN_APPROVAL"
    ASK_CLARIFICATION = "ASK_CLARIFICATION"
    REJECT = "REJECT"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Decision(BaseModel):
    action: Action
    risk_level: RiskLevel
    requires_human_approval: bool
    reason: str
    triggered_rules: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
