"""Mock carrier behaviour: deterministic timelines and honest labeling."""

from __future__ import annotations

import pytest
from atomc_plugin_orders.carriers import MOCK_CARRIER_NAME, MOCK_TIMELINES, MockCarrier
from atomc_plugin_orders.clock import FixedClock


async def test_known_number_returns_deterministic_timeline() -> None:
    clock = FixedClock()
    carrier = MockCarrier(clock)
    assert carrier.name == MOCK_CARRIER_NAME
    assert carrier.mock is True
    update = await carrier.track("MOCK-TRACK-1001")
    assert update.mock is True
    assert update.found is True
    assert [event.status for event in update.events] == ["shipped", "delivered"]
    assert update.events[0].at.isoformat() == "2025-12-30T00:00:00+00:00"
    assert update.events[1].at.isoformat() == "2026-01-01T00:00:00+00:00"
    assert update.latest is update.events[1]


async def test_timeline_is_stable_for_the_same_clock() -> None:
    carrier = MockCarrier(FixedClock())
    first = await carrier.track("MOCK-TRACK-3003")
    second = await carrier.track("MOCK-TRACK-3003")
    assert first == second


async def test_unknown_number_is_not_found_but_still_mock() -> None:
    update = await MockCarrier(FixedClock()).track("MOCK-NOPE")
    assert update.found is False
    assert update.mock is True
    assert update.events == ()
    assert update.latest is None
    assert "MOCK-TRACK-1001" in (update.message or "")


async def test_every_fixture_event_carries_a_note() -> None:
    carrier = MockCarrier(FixedClock())
    for number in MOCK_TIMELINES:
        update = await carrier.track(number)
        assert all(event.note for event in update.events)


@pytest.mark.parametrize("number", sorted(MOCK_TIMELINES))
async def test_known_numbers_are_listed(number: str) -> None:
    assert number in MockCarrier(FixedClock()).known_numbers()
