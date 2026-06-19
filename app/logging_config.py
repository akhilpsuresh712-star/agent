"""Logging setup — stdout, env-configurable, Docker-friendly.

Everything logs to **stdout** so `docker logs` / `docker compose logs` capture the
full run trace with no files inside the container. Verbosity is controlled by
`PROCUREMENT_LOG_LEVEL` (default `INFO`; set `DEBUG` to also see the raw planner
intent and validation failures).

Configured once, idempotently, under the `procurement` namespace with propagation
turned off, so our domain logs never double-print against uvicorn's own loggers
(`uvicorn`, `uvicorn.access`) — those keep emitting HTTP-level lines separately.
"""

from __future__ import annotations

import logging
import os
import sys

_NAMESPACE = "procurement"
_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    level_name = os.getenv("PROCUREMENT_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logger = logging.getLogger(_NAMESPACE)
    logger.setLevel(level)
    logger.propagate = False  # don't bubble to root / uvicorn's handlers
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-7s %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger (e.g. get_logger('procurement.harness'))."""
    configure_logging()
    return logging.getLogger(name)
