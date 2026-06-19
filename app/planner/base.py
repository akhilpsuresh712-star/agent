"""Planner contract. Both the rule-based and LLM planners implement this.

A planner turns a free-text message + department into a *proposed* intent. It is
untrusted: the harness re-validates whatever it returns against ProposedIntent
before using it. A planner never decides risk and never names a tool.
"""

from __future__ import annotations

from typing import Protocol

from app.schemas.intent import ProposedIntent


class Planner(Protocol):
    name: str

    def parse(self, message: str, department: str) -> ProposedIntent:
        ...
