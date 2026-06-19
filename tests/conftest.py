from __future__ import annotations

import pytest

from app.fixtures_loader import load_fixtures
from app.harness.runtime import AgentHarness
from app.planner.rule_based import RuleBasedPlanner


@pytest.fixture()
def fixtures():
    return load_fixtures("fixtures")


@pytest.fixture()
def harness(fixtures):
    return AgentHarness(planner=RuleBasedPlanner(), fixtures=fixtures)
