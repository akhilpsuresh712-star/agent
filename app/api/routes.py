"""HTTP surface — deliberately THIN. No business logic lives here; every route
delegates to the AgentHarness. The harness is resolved from app.state so a single
shared run store backs /run and /approve.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.harness.runtime import (
    AgentHarness,
    ApprovalGateError,
    InvalidTransitionError,
    RunNotFoundError,
)
from app.schemas.output import AgentRunRequest, AgentRunResponse

router = APIRouter()


def _harness(request: Request) -> AgentHarness:
    return request.app.state.harness


@router.post("/agent/run", response_model=AgentRunResponse)
def agent_run(body: AgentRunRequest, request: Request) -> AgentRunResponse:
    return _harness(request).run(body)


@router.post("/agent/runs/{run_id}/approve", response_model=AgentRunResponse)
def agent_approve(run_id: str, request: Request) -> AgentRunResponse:
    harness = _harness(request)
    try:
        return harness.approve(run_id)
    except RunNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ApprovalGateError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/agent/runs/{run_id}/reject", response_model=AgentRunResponse)
def agent_reject(run_id: str, request: Request) -> AgentRunResponse:
    harness = _harness(request)
    try:
        return harness.reject(run_id)
    except RunNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}
