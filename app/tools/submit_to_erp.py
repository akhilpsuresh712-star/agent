"""submit_to_erp — push an APPROVED purchase order to the ERP (mock).

The state gate (run must be APPROVED) is enforced by the harness, not here:
this tool is structurally unreachable except from the approval path. It only
performs the side effect.
"""

from __future__ import annotations

import uuid

from app.schemas.tools_io import DraftPO, SubmitToErpInput, SubmitToErpOutput


def submit_to_erp(inp: SubmitToErpInput) -> SubmitToErpOutput:
    submitted = inp.draft_po.model_copy(update={"status": "SUBMITTED"})
    return SubmitToErpOutput(
        erp_reference=f"ERP-{uuid.uuid4().hex[:10].upper()}",
        submitted_po=submitted,
    )
