"""lookup_catalog — resolve a raw item phrase against the catalog."""

from __future__ import annotations

from app.fixtures_loader import Fixtures
from app.schemas.tools_io import LookupCatalogInput, LookupCatalogOutput


def lookup_catalog(fixtures: Fixtures, inp: LookupCatalogInput) -> LookupCatalogOutput:
    item, alias = fixtures.resolve_item(inp.item_query)
    if item is None:
        return LookupCatalogOutput(resolved=False)
    return LookupCatalogOutput(
        resolved=True,
        item_id=item.id,
        name=item.name,
        category=item.category,
        unit_price_usd=item.unit_price_usd,
        matched_alias=alias,
    )
