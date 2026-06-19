"""FastAPI app factory + planner selection.

The planner is chosen at startup from PROCUREMENT_PLANNER (rule | llm). The
rule-based planner is the default and requires no external service. The LLM
planner is constructed lazily and only if explicitly selected, so importing /
running the app never depends on the OpenAI SDK or an API key.
"""

from __future__ import annotations

import os

from fastapi import FastAPI

from app.api.routes import router
from app.fixtures_loader import load_fixtures
from app.harness.runtime import AgentHarness
from app.planner.base import Planner


def build_planner(kind: str | None = None) -> Planner:
    kind = (kind or os.getenv("PROCUREMENT_PLANNER", "rule")).lower()
    if kind in ("llm", "groq"):
        from app.planner.llm import LLMPlanner

        return LLMPlanner()
    from app.planner.rule_based import RuleBasedPlanner

    return RuleBasedPlanner()


def create_app(*, planner: Planner | None = None, fixtures_dir: str | None = None) -> FastAPI:
    fixtures = load_fixtures(fixtures_dir)
    harness = AgentHarness(planner=planner or build_planner(), fixtures=fixtures)

    app = FastAPI(title="Procurement Approval Agent", version="0.1.0")
    app.state.harness = harness
    app.include_router(router)
    return app


# uvicorn entrypoint: `uvicorn app.main:app`
app = create_app()
