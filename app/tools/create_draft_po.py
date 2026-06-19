"""create_draft_po — build a draft purchase order. Never submits."""

from __future__ import annotations

import uuid

from app.schemas.tools_io import CreateDraftPOInput, DraftPO


def create_draft_po(inp: CreateDraftPOInput) -> DraftPO:
    return DraftPO(
        po_number=f"PO-{uuid.uuid4().hex[:8].upper()}",
        item_id=inp.item_id,
        name=inp.name,
        category=inp.category,
        quantity=inp.quantity,
        unit_price_usd=inp.unit_price_usd,
        total_usd=round(inp.quantity * inp.unit_price_usd, 2),
        department=inp.department,
        status="DRAFT",
    )
