"""Injectable clocks and RFC 3339 timestamp formatting.

Every history entry the plugin writes carries a timestamp from a :class:`Clock`, so tests can
drive the ledger deterministically instead of depending on wall-clock time.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable

__all__ = [
    "Clock",
    "FixedClock",
    "SystemClock",
    "format_timestamp",
    "parse_timestamp",
]


def format_timestamp(value: datetime) -> str:
    """Serialise a UTC datetime as ``YYYY-MM-DDTHH:MM:SSZ`` (IR canonical form)."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_timestamp(value: str) -> datetime:
    """Parse an RFC 3339 timestamp, normalising ``Z`` to ``+00:00``.

    Raises :class:`ValueError` on malformed input so callers can surface a structured failure.
    """
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware (RFC 3339 UTC)")
    return parsed.astimezone(UTC)


@runtime_checkable
class Clock(Protocol):
    """A source of the current instant, injectable for tests."""

    def now(self) -> datetime:
        """Return the current timezone-aware UTC instant."""
        ...


class SystemClock:
    """Wall-clock :class:`Clock`."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """A manually advanced clock; starts at ``start`` (default 2026-01-01T00:00:00Z)."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 1, 1, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs: float) -> datetime:
        """Advance the clock by ``timedelta`` keyword arguments (``days=``, ``hours=``, …)."""
        self._now = self._now + timedelta(**kwargs)
        return self._now

    def set(self, value: datetime) -> datetime:
        """Set the clock to an explicit timezone-aware instant."""
        if value.tzinfo is None:
            raise ValueError("FixedClock.set requires a timezone-aware datetime")
        self._now = value.astimezone(UTC)
        return self._now
