"""The harness emits a stdout log trace for a run (run start, each tool call,
final decision). We attach a capturing handler directly to the `procurement`
logger because it is configured with propagate=False (so it never double-prints
against uvicorn) — which means pytest's `caplog` (root-based) would not see it.
"""

from __future__ import annotations

import logging

from app.schemas.output import AgentRunRequest


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def test_run_emits_lifecycle_logs(harness):
    logger = logging.getLogger("procurement")
    handler = _ListHandler()
    logger.addHandler(handler)
    try:
        r = harness.run(
            AgentRunRequest(
                message="Please buy 2 MacBook Pro for engineering.", department="engineering"
            )
        )
    finally:
        logger.removeHandler(handler)

    blob = "\n".join(handler.messages)
    assert f"run {r.run_id} START" in blob
    assert "tool lookup_catalog" in blob
    assert "tool check_policy" in blob
    assert f"run {r.run_id} DECISION=NEED_HUMAN_APPROVAL" in blob


def test_gate_refusal_is_logged(harness):
    """A blocked submit_to_erp logs at WARNING and is captured in the trace."""
    logger = logging.getLogger("procurement")
    handler = _ListHandler()
    handler.setLevel(logging.WARNING)
    logger.addHandler(handler)
    try:
        r = harness.run(
            AgentRunRequest(
                message="Please buy 2 MacBook Pro for engineering.", department="engineering"
            )
        )
        try:
            harness.submit_to_erp(r.run_id)  # not APPROVED -> refused
        except Exception:
            pass
    finally:
        logger.removeHandler(handler)

    assert any("blocked: run not approved" in m for m in handler.messages)
