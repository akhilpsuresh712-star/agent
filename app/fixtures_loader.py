"""Loads catalog / policies / budgets once and exposes a small domain model.

This is the ONLY module coupled to the on-disk fixture JSON shapes. If the
fixtures change format, this file is the single place to adapt; everything
downstream consumes the typed `Fixtures` object below.

Expected fixture shapes (from the take-home):
    catalog.json   : [ {id, name, aliases[], unit_price, category}, ... ]
    policies.json  : {approval_threshold_usd, restricted_categories[], rules[{id, description}]}
    budgets.json   : { "<department>": {"remaining_budget_usd": <num>}, ... }
    sample_requests.json (used by demo/tests only)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel


# --- typed domain model ---------------------------------------------------
class CatalogItem(BaseModel):
    id: str
    name: str
    aliases: list[str]
    unit_price_usd: float
    category: str


class PolicyConfig(BaseModel):
    approval_threshold_usd: float
    restricted_categories: list[str]
    # rule id -> human-readable description, for auditable reasons in the trace
    rule_descriptions: dict[str, str] = {}


@dataclass
class Fixtures:
    items: list[CatalogItem]
    policy: PolicyConfig
    budgets: dict[str, float]  # department -> remaining budget USD
    _alias_index: list[tuple[str, CatalogItem]] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Pre-build (alias, item) pairs sorted longest-alias-first so the most
        # specific match wins (e.g. "macbook pro" beats "macbook").
        pairs: list[tuple[str, CatalogItem]] = []
        for item in self.items:
            for alias in [item.name, *item.aliases]:
                pairs.append((alias.lower(), item))
        pairs.sort(key=lambda p: len(p[0]), reverse=True)
        self._alias_index = pairs

    def resolve_item(self, query: str) -> tuple[CatalogItem | None, str | None]:
        """Resolve a raw phrase to a catalog item via substring alias match.

        Returns (item, matched_alias) or (None, None). Case-insensitive; works
        when the item name appears in Latin script inside an otherwise non-Latin
        (e.g. Chinese) message, which is exactly the fixture situation.
        """
        if not query:
            return None, None
        haystack = query.lower()
        for alias, item in self._alias_index:  # longest alias first
            if alias in haystack:
                return item, alias
        return None, None

    def budget_remaining(self, department: str) -> float:
        # Unknown department => no budget available => treated as 0 (over-budget).
        return float(self.budgets.get(department.lower(), 0.0))


# --- loading --------------------------------------------------------------
def _read_json(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_fixtures(fixtures_dir: str | os.PathLike | None = None) -> Fixtures:
    base = Path(fixtures_dir or os.getenv("PROCUREMENT_FIXTURES_DIR", "fixtures"))
    if not base.exists():
        raise FileNotFoundError(
            f"Fixtures directory not found: {base.resolve()} "
            "(set PROCUREMENT_FIXTURES_DIR or pass fixtures_dir)."
        )

    raw_catalog = _read_json(base / "catalog.json")
    items = [
        CatalogItem(
            id=row["id"],
            name=row["name"],
            aliases=row.get("aliases", []),
            unit_price_usd=float(row["unit_price"]),
            category=row["category"],
        )
        for row in raw_catalog
    ]

    raw_policy = _read_json(base / "policies.json")
    policy = PolicyConfig(
        approval_threshold_usd=float(raw_policy["approval_threshold_usd"]),
        restricted_categories=list(raw_policy.get("restricted_categories", [])),
        rule_descriptions={r["id"]: r["description"] for r in raw_policy.get("rules", [])},
    )

    raw_budgets = _read_json(base / "budgets.json")
    budgets = {dept.lower(): float(v["remaining_budget_usd"]) for dept, v in raw_budgets.items()}

    return Fixtures(items=items, policy=policy, budgets=budgets)


def load_sample_requests(fixtures_dir: str | os.PathLike | None = None) -> list[dict]:
    base = Path(fixtures_dir or os.getenv("PROCUREMENT_FIXTURES_DIR", "fixtures"))
    return _read_json(base / "sample_requests.json")
