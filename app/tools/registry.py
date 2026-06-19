"""Explicit tool registry — the single place tools are registered AND the path
every tool dispatch goes through.

"Where is the tool registry?" has a one-line answer: here. Each `ToolSpec` binds
a tool name to (a) its pydantic input model — so the harness validates any
payload *before* the tool runs (guardrail 5B) — and (b) a callable already bound
to its domain dependencies (fixtures, policy engine). The harness builds the
registry once at startup and routes every tool call through it, so the
tool-calling flow has one verifiable chokepoint rather than four direct imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel

from app.fixtures_loader import Fixtures
from app.policy.engine import PolicyEngine
from app.schemas.tools_io import (
    CheckPolicyInput,
    CreateDraftPOInput,
    LookupCatalogInput,
    SubmitToErpInput,
)
from app.tools.check_policy import check_policy as _check_policy
from app.tools.create_draft_po import create_draft_po as _create_draft_po
from app.tools.lookup_catalog import lookup_catalog as _lookup_catalog
from app.tools.submit_to_erp import submit_to_erp as _submit_to_erp


@dataclass(frozen=True)
class ToolSpec:
    """A registered tool: its name, the input model used to validate payloads,
    and a callable that takes a *validated* input and returns the tool output."""

    name: str
    input_model: type[BaseModel]
    run: Callable[[BaseModel], object]


def build_tool_registry(fixtures: Fixtures, policy: PolicyEngine) -> dict[str, ToolSpec]:
    """Construct the name -> ToolSpec registry. Domain dependencies (the loaded
    fixtures and the policy engine) are bound here, so callers dispatch every
    tool through one uniform `(validated_input) -> output` interface."""
    return {
        "lookup_catalog": ToolSpec(
            "lookup_catalog", LookupCatalogInput, lambda inp: _lookup_catalog(fixtures, inp)
        ),
        "check_policy": ToolSpec(
            "check_policy", CheckPolicyInput, lambda inp: _check_policy(policy, inp)
        ),
        "create_draft_po": ToolSpec("create_draft_po", CreateDraftPOInput, _create_draft_po),
        "submit_to_erp": ToolSpec("submit_to_erp", SubmitToErpInput, _submit_to_erp),
    }


# name -> input model, for introspection / tests that don't need a bound registry.
TOOL_INPUT_MODELS: dict[str, type[BaseModel]] = {
    "lookup_catalog": LookupCatalogInput,
    "check_policy": CheckPolicyInput,
    "create_draft_po": CreateDraftPOInput,
    "submit_to_erp": SubmitToErpInput,
}

TOOL_NAMES = tuple(TOOL_INPUT_MODELS.keys())
