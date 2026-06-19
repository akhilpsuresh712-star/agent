"""Run state + in-memory store.

The store is a dict keyed by run_id — fine for this exercise. In production this
would be Redis or a database so approval can happen across processes/restarts;
the RunStore interface is deliberately the only thing that would change.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.schemas.decision import Decision
from app.schemas.intent import ProposedIntent
from app.schemas.output import AgentRunRequest, RunStatus
from app.schemas.tools_io import DraftPO, ToolCallRecord


@dataclass
class RunState:
    run_id: str
    request: AgentRunRequest
    status: RunStatus = RunStatus.CREATED
    intent: ProposedIntent | None = None
    decision: Decision | None = None
    draft_po: DraftPO | None = None
    trace: list[ToolCallRecord] = field(default_factory=list)

    def record(self, rec: ToolCallRecord) -> None:
        self.trace.append(rec)


class RunStore:
    """In-memory run store. Swap for Redis/DB in production."""

    def __init__(self) -> None:
        self._runs: dict[str, RunState] = {}

    def create(self, request: AgentRunRequest) -> RunState:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        state = RunState(run_id=run_id, request=request)
        self._runs[run_id] = state
        return state

    def get(self, run_id: str) -> RunState | None:
        return self._runs.get(run_id)
