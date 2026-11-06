"""Carrier interface and tracking value objects.

A real carrier adapter (none ships yet) would implement :class:`Carrier` and return
:class:`TrackingUpdate` objects with the same shape. Every update carries an explicit ``mock``
flag so no caller can mistake simulated tracking for a real shipment event.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

__all__ = ["Carrier", "TrackingEvent", "TrackingUpdate"]


@dataclass(frozen=True)
class TrackingEvent:
    """One carrier-reported event on a shipment timeline."""

    status: str
    at: datetime
    note: str | None = None
    location: str | None = None


@dataclass(frozen=True)
class TrackingUpdate:
    """The result of asking a carrier about one tracking number."""

    carrier: str
    number: str
    mock: bool
    found: bool
    events: tuple[TrackingEvent, ...] = field(default_factory=tuple)
    message: str | None = None

    @property
    def latest(self) -> TrackingEvent | None:
        """Return the most recent event, or ``None`` when there is no timeline."""
        if not self.events:
            return None
        return max(self.events, key=lambda event: event.at)


@runtime_checkable
class Carrier(Protocol):
    """A tracking source. Implementations must not perform network I/O when ``mock`` is true."""

    @property
    def name(self) -> str:
        """Carrier identifier (e.g. ``mock``)."""
        ...

    @property
    def mock(self) -> bool:
        """Whether this carrier is a simulation that must be labeled as such."""
        ...

    async def track(self, number: str) -> TrackingUpdate:
        """Return the tracking timeline for ``number``."""
        ...
