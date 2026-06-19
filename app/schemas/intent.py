"""The ProposedIntent — the ONLY thing a planner is allowed to return.

By design this carries no risk level, no action, and no tool name. The planner
(rule-based or LLM) proposes *what the user seems to want*; the harness and the
deterministic policy engine decide what, if anything, happens. This boundary is
the whole prompt-injection defense: a planner cannot escalate privilege because
the shape of its output gives it no field in which to do so.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ProposedIntent(BaseModel):
    """A claim about user intent, validated before the harness trusts it."""

    item_query: str = Field(..., description="Raw item phrase; resolved later via catalog aliases.")
    quantity: int | None = Field(None, description="None => a required field is missing => ASK_CLARIFICATION.")
    department: str = Field(..., description="Budget-owning department, taken from the request (not parsed).")
    budget_hint_usd: float | None = Field(None, description="User's stated cap. Advisory only — never authoritative.")
    raw_message: str = Field(..., description="Original message, kept for the bypass detector and audit trail.")

    @field_validator("quantity")
    @classmethod
    def _non_positive_is_missing(cls, v: int | None) -> int | None:
        # A planner that emits 0 or a negative quantity has given us nothing usable.
        # Treat it as "missing" so it routes to clarification rather than blowing up
        # deeper in the pipeline. The tool layer enforces >= 1 a second time (5B).
        if v is not None and v <= 0:
            return None
        return v
