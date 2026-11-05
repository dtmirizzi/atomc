"""In-process event bus with per-connection subscriptions and bounded backpressure.

Events are best-effort and ordered per WebSocket connection. There is **no durable replay**:
reconnecting clients re-fetch state via ``ir.get`` / ``dag.status`` / ``gates.list``.

Backpressure policy: every connection has a bounded queue (default 1024). When a slow client
fills it, the **oldest** event is dropped and a ``log``-level warning is emitted; the newest
event is always retained. This keeps producers non-blocking at the cost of lossy delivery for
pathologically slow consumers.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import Any

from .common import utcnow_iso

DEFAULT_QUEUE_SIZE = 1024

#: Topics defined by the RPC contract.
KNOWN_TOPICS = ("ir.changed", "gate.result", "dag.node.start", "dag.node.end", "log")


@dataclass
class Event:
    """A single pushed notification."""

    topic: str
    data: dict[str, Any]
    ts: str = field(default_factory=utcnow_iso)


@dataclass
class Subscription:
    id: str
    topics: frozenset[str]
    queue: asyncio.Queue[Event]


class EventBus:
    """Fan-out bus. One subscription queue per ``events.subscribe`` call."""

    def __init__(self, queue_size: int = DEFAULT_QUEUE_SIZE) -> None:
        self._queue_size = queue_size
        self._subscriptions: dict[str, Subscription] = {}
        self._counter = 0
        self.dropped = 0
        self._logger: Any = None

    def set_logger(self, logger: Any) -> None:
        self._logger = logger

    def subscribe(self, topics: list[str]) -> Subscription:
        """Create a subscription for ``topics`` (unknown topics are allowed but never fire)."""
        self._counter += 1
        sub_id = f"sub-{self._counter}"
        sub = Subscription(
            id=sub_id,
            topics=frozenset(topics),
            queue=asyncio.Queue(maxsize=self._queue_size),
        )
        self._subscriptions[sub_id] = sub
        return sub

    def unsubscribe(self, subscription_id: str) -> bool:
        """Remove a subscription. Returns True if it existed."""
        return self._subscriptions.pop(subscription_id, None) is not None

    def add_subscription(self, sub: Subscription) -> None:
        """Register an externally created subscription (used by tests)."""
        self._subscriptions[sub.id] = sub

    def publish(self, topic: str, data: dict[str, Any]) -> None:
        """Publish an event to every matching subscription (non-blocking)."""
        if topic not in KNOWN_TOPICS:
            raise ValueError(f"unknown event topic {topic!r}")
        event = Event(topic=topic, data=data)
        for sub in list(self._subscriptions.values()):
            if topic not in sub.topics:
                continue
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                self.dropped += 1
                with contextlib.suppress(asyncio.QueueEmpty):  # pragma: no cover - race
                    sub.queue.get_nowait()
                sub.queue.put_nowait(event)
                if self._logger is not None:
                    self._logger.warning(
                        "event_queue_overflow",
                        topic=topic,
                        subscription=sub.id,
                        dropped_total=self.dropped,
                    )

    def subscriptions(self) -> list[str]:
        return list(self._subscriptions)

    def clear(self) -> None:
        self._subscriptions.clear()


__all__ = [
    "DEFAULT_QUEUE_SIZE",
    "KNOWN_TOPICS",
    "Event",
    "EventBus",
    "Subscription",
]
