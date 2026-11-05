"""Structured logging setup for ``atomcd``.

Always emits JSON to stdout/stderr; bearer tokens and other secrets are never bound to log
records. Internal RPC failures log the full stack here while clients receive only an opaque
request id.
"""

from __future__ import annotations

from typing import Any

import structlog


def configure_logging(level: str = "info") -> None:
    """Configure structlog once at daemon startup."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(sort_keys=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(_level_number(level)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "atomcd") -> Any:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)


def _level_number(level: str) -> int:
    import logging

    return getattr(logging, level.upper(), logging.INFO)


__all__ = ["configure_logging", "get_logger"]
