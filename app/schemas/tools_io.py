"""Per-tool input/output models.

Each tool validates its OWN input with a pydantic model. This is guardrail 5B:
the planner's proposal is never trusted as tool input — it must survive the tool's
schema first. Negative/zero quantities and negative prices are rejected here even
if every layer above somehow let them through.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.decision import Decision


# --- lookup_catalog -------------------------------------------------------
class LookupCatalogInput(BaseModel):
    item_query: str = Field(..., min_length=1)


class LookupCatalogOutput(BaseModel):
    resolved: bool
    item_id: str | None = None
    name: str | None = None
    category: str | None = None
    unit_price_usd: float | None = None
    matched_alias: str | None = None


# --- check_policy ---------------------------------------------------------
class CheckPolicyInput(BaseModel):
    category: str
    amount_usd: float = Field(..., ge=0)
    quantity: int = Field(..., ge=1)
    budget_remaining_usd: float = Field(..., ge=0)
    bypass_detected: bool = False


# check_policy returns a Decision (see decision.py).


# --- create_draft_po ------------------------------------------------------
class CreateDraftPOInput(BaseModel):
    item_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    category: str
    quantity: int = Field(..., ge=1)
    unit_price_usd: float = Field(..., ge=0)
    department: str = Field(..., min_length=1)


class DraftPO(BaseModel):
    po_number: str
    item_id: str
    name: str
    category: str
    quantity: int
    unit_price_usd: float
    total_usd: float
    department: str
    currency: str = "USD"
    status: str = "DRAFT"  # DRAFT -> SUBMITTED (after approval)


# --- submit_to_erp --------------------------------------------------------
class SubmitToErpInput(BaseModel):
    draft_po: DraftPO


class SubmitToErpOutput(BaseModel):
    erp_reference: str
    submitted_po: DraftPO


# --- trace record ---------------------------------------------------------
class ToolCallRecord(BaseModel):
    tool: str
    ok: bool
    status: str  # short human-readable status, e.g. "resolved", "blocked: not approved"
    args_summary: str
