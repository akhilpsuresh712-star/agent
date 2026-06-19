"""End-to-end HTTP test: the thin routes wire through to the harness and share a
single run store across /run and /approve.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client():
    app = create_app(fixtures_dir="fixtures")
    return TestClient(app)


def test_run_then_approve_arc(client):
    resp = client.post(
        "/agent/run",
        json={"message": "Please buy 2 MacBook Pro for engineering.", "department": "engineering"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "NEEDS_APPROVAL"
    run_id = body["run_id"]

    approved = client.post(f"/agent/runs/{run_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "SUBMITTED"


def test_low_risk_run_returns_draft(client):
    resp = client.post(
        "/agent/run",
        json={"message": "Please order 3 Figma Enterprise seats for marketing.", "department": "marketing"},
    )
    body = resp.json()
    assert body["status"] == "COMPLETED"
    assert body["draft_po"]["total_usd"] == 2400


def test_approve_unknown_run_404(client):
    assert client.post("/agent/runs/run_does_not_exist/approve").status_code == 404
