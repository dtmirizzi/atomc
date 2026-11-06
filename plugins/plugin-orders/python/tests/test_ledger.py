"""Order-ledger state machine and record helpers."""

from __future__ import annotations

from typing import Any

import pytest
from atomc_plugin_orders.clock import FixedClock
from atomc_plugin_orders.errors import IllegalTransitionError
from atomc_plugin_orders.ledger import (
    ALLOWED_TRANSITIONS,
    ORDER_STATUSES,
    append_history,
    can_transition,
    find_order,
    find_order_by_tracking,
    history_entry,
    new_order,
    next_order_id,
    order_lines,
    order_total,
    slugify,
    validate_transition,
)


def test_status_set_matches_the_frozen_contract() -> None:
    assert set(ORDER_STATUSES) == {
        "draft",
        "placed",
        "paid",
        "shipped",
        "delivered",
        "cancelled",
    }
    assert set(ALLOWED_TRANSITIONS) == set(ORDER_STATUSES)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("draft", "placed"),
        ("draft", "cancelled"),
        ("placed", "paid"),
        ("placed", "cancelled"),
        ("paid", "shipped"),
        ("paid", "cancelled"),
        ("shipped", "delivered"),
    ],
)
def test_legal_transitions(current: str, target: str) -> None:
    assert can_transition(current, target)
    validate_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("draft", "paid"),
        ("draft", "shipped"),
        ("draft", "delivered"),
        ("placed", "shipped"),
        ("paid", "delivered"),
        ("shipped", "cancelled"),
        ("delivered", "cancelled"),
        ("cancelled", "draft"),
        ("delivered", "shipped"),
        ("paid", "paid"),
    ],
)
def test_illegal_transitions(current: str, target: str) -> None:
    assert not can_transition(current, target)
    with pytest.raises(IllegalTransitionError) as excinfo:
        validate_transition(current, target)
    assert excinfo.value.current == current
    assert excinfo.value.target == target
    assert "no vendor was contacted" in str(excinfo.value)


def test_unknown_status_is_rejected() -> None:
    with pytest.raises(IllegalTransitionError):
        validate_transition("bogus", "placed")


def test_new_order_is_a_draft_with_history_and_total() -> None:
    clock = FixedClock()
    order = new_order(
        order_id="order:draft_lcsc",
        vendor="lcsc",
        kind="parts",
        lines=[{"sku": "C1", "qty": 2, "unit_price_minor": 50}],
        currency="USD",
        clock=clock,
        note="hello",
    )
    assert order["id"] == "order:draft_lcsc"
    assert order["status"] == "draft"
    assert order["total_minor"] == 100
    assert order["lines"] == [{"sku": "C1", "qty": 2, "unit_price_minor": 50}]
    assert order["history"] == [{"at": "2026-01-01T00:00:00Z", "status": "draft", "note": "hello"}]
    assert order["tracking"] == []
    assert "external_id" not in order


def test_history_entries_use_the_injected_clock() -> None:
    clock = FixedClock()
    first = history_entry(clock, "draft", "one")
    clock.advance(days=2)
    second = history_entry(clock, "placed", "two")
    assert first["at"] == "2026-01-01T00:00:00Z"
    assert second["at"] == "2026-01-03T00:00:00Z"
    order = append_history({"history": [first]}, second)
    assert [entry["status"] for entry in order["history"]] == ["draft", "placed"]


def test_order_lines_and_total_validate() -> None:
    lines = order_lines([{"sku": " A ", "qty": 3, "unit_price_minor": 2}])
    assert lines == [{"sku": "A", "qty": 3, "unit_price_minor": 2}]
    assert order_total(lines) == 6
    with pytest.raises(ValueError, match="sku"):
        order_lines([{"sku": "", "qty": 1}])
    with pytest.raises(ValueError, match="qty"):
        order_lines([{"sku": "A", "qty": 0}])


def test_find_helpers() -> None:
    orders: list[dict[str, Any]] = [
        {"id": "order:a", "tracking": [{"carrier": "mock", "number": "MOCK-TRACK-1001"}]},
        {"id": "order:b", "tracking": []},
    ]
    assert find_order(orders, "order:a") is not None
    assert find_order(orders, "order:zzz") is None
    found = find_order_by_tracking(orders, "MOCK-TRACK-1001")
    assert found is not None
    assert found["id"] == "order:a"
    assert find_order_by_tracking(orders, "nope") is None


def test_next_order_id_is_deterministic_and_unique() -> None:
    assert next_order_id([], "lcsc") == "order:draft_lcsc"
    existing = [{"id": "order:draft_lcsc"}, {"id": "order:draft_lcsc_2"}]
    assert next_order_id(existing, "lcsc") == "order:draft_lcsc_3"
    assert slugify("Digi-Key") == "digi_key"
    assert slugify("  ") == "vendor"
