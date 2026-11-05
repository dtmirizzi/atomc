"""Event bus: subscription filtering, unsubscribe, overflow/backpressure."""

from __future__ import annotations

import asyncio

import pytest
from atomcd.events import EventBus


async def test_publish_only_matching_topics() -> None:
    bus = EventBus()
    ir_sub = bus.subscribe(["ir.changed"])
    gate_sub = bus.subscribe(["gate.result"])
    bus.publish("ir.changed", {"rev": 1})
    assert ir_sub.queue.get_nowait().data == {"rev": 1}
    assert gate_sub.queue.empty()


def test_unsubscribe() -> None:
    bus = EventBus()
    sub = bus.subscribe(["log"])
    assert bus.unsubscribe(sub.id) is True
    assert bus.unsubscribe(sub.id) is False
    bus.publish("log", {"level": "info", "msg": "x"})
    assert sub.queue.empty()


def test_unknown_topic_rejected() -> None:
    bus = EventBus()
    with pytest.raises(ValueError, match="unknown event topic"):
        bus.publish("nope.topic", {})


def test_overflow_drops_oldest_and_keeps_newest() -> None:
    bus = EventBus(queue_size=2)
    sub = bus.subscribe(["log"])
    for i in range(5):
        bus.publish("log", {"level": "info", "msg": str(i)})
    assert sub.queue.qsize() == 2
    newest = sub.queue.get_nowait()
    assert newest.data["msg"] == "3"
    assert bus.dropped == 3


def test_clear_removes_subscriptions() -> None:
    bus = EventBus()
    sub = bus.subscribe(["log"])
    assert bus.subscriptions() == [sub.id]
    bus.clear()
    assert bus.subscriptions() == []


def test_queue_is_bounded() -> None:
    bus = EventBus(queue_size=1)
    sub = bus.subscribe(["log"])
    assert sub.queue.maxsize == 1
    assert isinstance(sub.queue, asyncio.Queue)
