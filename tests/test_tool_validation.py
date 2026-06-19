"""Per-tool input validation (guardrail 5B): the planner is never trusted as
tool input. A crafted bad payload must be rejected by the tool's own schema.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.tools_io import (
    CheckPolicyInput,
    CreateDraftPOInput,
    LookupCatalogInput,
)


def test_create_draft_po_rejects_zero_quantity():
    with pytest.raises(ValidationError):
        CreateDraftPOInput(
            item_id="x", name="x", category="hardware",
            quantity=0, unit_price_usd=10, department="eng",
        )


def test_create_draft_po_rejects_negative_quantity():
    with pytest.raises(ValidationError):
        CreateDraftPOInput(
            item_id="x", name="x", category="hardware",
            quantity=-3, unit_price_usd=10, department="eng",
        )


def test_create_draft_po_rejects_negative_price():
    with pytest.raises(ValidationError):
        CreateDraftPOInput(
            item_id="x", name="x", category="hardware",
            quantity=1, unit_price_usd=-5, department="eng",
        )


def test_check_policy_rejects_negative_amount():
    with pytest.raises(ValidationError):
        CheckPolicyInput(category="software", amount_usd=-1, quantity=1, budget_remaining_usd=100)


def test_lookup_rejects_empty_query():
    with pytest.raises(ValidationError):
        LookupCatalogInput(item_query="")


def test_planner_non_positive_quantity_becomes_missing():
    """Intent layer coerces a junk quantity to None so it routes to clarification."""
    from app.schemas.intent import ProposedIntent

    intent = ProposedIntent(item_query="x", quantity=0, department="eng", raw_message="x")
    assert intent.quantity is None


def test_harness_dispatches_every_tool_through_the_registry(harness):
    """The harness's tool table IS the registry — every tool flows through it."""
    from app.tools.registry import TOOL_NAMES

    assert set(harness.tools) == set(TOOL_NAMES)


def test_dispatch_validates_payload_against_registered_model(harness):
    """_dispatch validates via the registry's input model BEFORE running the tool,
    so a crafted bad payload (quantity=0) is rejected at the dispatch chokepoint."""
    with pytest.raises(ValidationError):
        harness._dispatch(
            "create_draft_po",
            item_id="x", name="x", category="hardware",
            quantity=0, unit_price_usd=10, department="eng",
        )
