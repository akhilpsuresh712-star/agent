"""Procurement approval agent package.

Loads `.env` on first import so every entry point — `uvicorn app.main`, the demo,
and direct `app.planner.llm` use — sees the same configuration. Real shell
environment variables always win (override=False), so an explicit `export` beats
the file. We honour the canonical project-root `.env` first and an optional
`app/.env` second. Soft-imported so the core app still runs with only
fastapi/pydantic/uvicorn installed; the LLM planner's keys are the only thing
that lives here, and that path is opt-in.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(_ROOT / ".env")
    load_dotenv(_ROOT / "app" / ".env")


_load_dotenv()

# Configure logging after .env so PROCUREMENT_LOG_LEVEL from the file is honoured.
from app.logging_config import configure_logging  # noqa: E402

configure_logging()
