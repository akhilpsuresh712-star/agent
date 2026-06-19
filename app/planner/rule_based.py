"""Deterministic, dependency-free planner. The DEFAULT — demo and tests never
need a live LLM.

It parses plain English requests:

  quantity    : the first number that is not a stated budget amount.
  budget hint : a number marked as money ($X, "X USD", "under X", "budget X").
  item_query  : the raw message; the catalog resolves it by substring alias match
                (so "buy 2 MacBook Pro" still finds the "macbook pro" alias).

The planner proposes only — it does not resolve the catalog, compute risk, or
choose a tool. That all happens deterministically downstream.
"""

from __future__ import annotations

import re

from app.schemas.intent import ProposedIntent

# A number that is a stated budget/price, e.g. "$3000", "3000 USD", "under 3000".
_BUDGET_AMOUNT = re.compile(
    r"\$\s*(\d[\d,]*)"
    r"|(\d[\d,]*)\s*(?:usd|dollars?)\b"
    r"|(?:under|below|budget|cap|capped at|up to|within|max(?:imum)?)\s+\$?\s*(\d[\d,]*)",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"\d[\d,]*")


def _to_int(s: str) -> int:
    return int(s.replace(",", ""))


def _extract_budget_hint(message: str) -> float | None:
    m = _BUDGET_AMOUNT.search(message)
    if not m:
        return None
    # Exactly one of the alternative groups captured the digits.
    digits = next(g for g in m.groups() if g)
    return float(_to_int(digits))


def _extract_quantity(message: str) -> int | None:
    # The first number that is not part of a stated budget amount is the quantity.
    budget_spans = [m.span() for m in _BUDGET_AMOUNT.finditer(message)]

    def _is_budget(num: re.Match) -> bool:
        return any(start <= num.start() < end for start, end in budget_spans)

    for num in _NUMBER.finditer(message):
        if not _is_budget(num):
            return _to_int(num.group())
    return None


class RuleBasedPlanner:
    name = "rule_based"

    def parse(self, message: str, department: str) -> ProposedIntent:
        return ProposedIntent(
            item_query=message,  # resolved downstream via catalog substring match
            quantity=_extract_quantity(message),
            department=department,
            budget_hint_usd=_extract_budget_hint(message),
            raw_message=message,
        )
