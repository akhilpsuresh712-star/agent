"""Run lifecycle status + the request/response envelope.

AgentRunResponse is the final guardrail (5A): every response leaving the API is
constructed as — and therefore validated against — this model.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.decision import Decision
from app.schemas.tools_io import DraftPO, ToolCallRecord


class RunStatus(str, Enum):
    # Lifecycle (see docs/ARCHITECTURE.md state machine)
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    VALIDATING_INTENT = "VALIDATING_INTENT"
    DECIDING = "DECIDING"
    # Terminal-ish
    COMPLETED = "COMPLETED"                    # draft created, NOT submitted
    NEEDS_APPROVAL = "NEEDS_APPROVAL"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    REJECTED = "REJECTED"
    # Approval branch
    APPROVED = "APPROVED"
    SUBMITTED = "SUBMITTED"


class AgentRunRequest(BaseModel):
    message: str = Field(..., min_length=1)
    department: str = Field(..., min_length=1)
    user_id: str | None = None


class AgentRunResponse(BaseModel):
    run_id: str
    status: RunStatus
    decision: Decision
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    draft_po: DraftPO | None = None
