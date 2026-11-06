"""Order-ledger semantics: the status state machine and order-record helpers.

All helpers here are pure; the plugin applies them through ``ir_transact`` so the daemon enforces
the plugin's ``/orders`` write scope. Statuses follow the frozen IR contract
(``packages/core-core-ir/python/src/atomc_core_ir/orders.py``):
``draft → placed → paid → shipped → delivered`` plus ``cancelled``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from .clock import Clock, format_timestamp
from .errors import IllegalTransitionError

__all__ = [
    "ALLOWED_TRANSITIONS",
    "ORDER_STATUSES",
    "TERMINAL_STATUSES",
    "append_history",
    "can_transition",
    "find_order",
    "find_order_by_tracking",
    "history_entry",
    "new_order",
    "next_order_id",
    "order_lines",
    "order_total",
    "slugify",
    "validate_transition",
]

ORDER_STATUSES: tuple[str, ...] = (
    "draft",
    "placed",
    "paid",
    "shipped",
    "delivered",
    "cancelled",
)
"""Every status the frozen ``Order`` model permits."""

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"placed", "cancelled"}),
    "placed": frozenset({"paid", "cancelled"}),
    "paid": frozenset({"shipped", "cancelled"}),
    "shipped": frozenset({"delivered"}),
    "delivered": frozenset(),
    "cancelled": frozenset(),
}
"""Legal status transitions. ``shipped``/``delivered`` cannot be cancelled (goods are in flight)."""

TERMINAL_STATUSES: frozenset[str] = frozenset({"delivered", "cancelled"})

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def can_transition(current: str, target: str) -> bool:
    """Return whether ``current -> target`` is legal."""
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def validate_transition(current: str, target: str) -> None:
    """Raise :class:`IllegalTransitionError` unless ``current -> target`` is legal.

    A no-op transition (``current == target``) is treated as illegal: callers that re-apply an
    event they already recorded must dedupe instead of silently re-transitioning.
    """
    if current not in ALLOWED_TRANSITIONS:
        raise IllegalTransitionError(current, target)
    if not can_transition(current, target):
        raise IllegalTransitionError(current, target)


def slugify(value: str) -> str:
    """Lower-case a vendor/file name to a safe ``[a-z0-9_]`` slug."""
    slug = _SLUG_RE.sub("_", value.strip().lower()).strip("_")
    return slug or "vendor"


def history_entry(clock: Clock, status: str, note: str | None = None) -> dict[str, Any]:
    """Build a history entry with a timestamp from ``clock``."""
    entry: dict[str, Any] = {"at": format_timestamp(clock.now()), "status": status}
    if note is not None:
        entry["note"] = note
    return entry


def append_history(order: Mapping[str, Any], entry: Mapping[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of ``order`` with ``entry`` appended to its history."""
    updated = dict(order)
    history = list(updated.get("history") or [])
    history.append(dict(entry))
    updated["history"] = history
    return updated


def order_lines(lines: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Normalise arbitrary line mappings to the frozen ``OrderLine`` shape."""
    normalised: list[dict[str, Any]] = []
    for line in lines:
        sku = str(line.get("sku") or "").strip()
        if not sku:
            raise ValueError("order line requires a non-empty 'sku'")
        qty = int(line.get("qty") or 0)
        if qty < 1:
            raise ValueError(f"order line {sku!r} requires qty >= 1")
        price = int(line.get("unit_price_minor") or 0)
        if price < 0:
            raise ValueError(f"order line {sku!r} requires unit_price_minor >= 0")
        normalised.append({"sku": sku, "qty": qty, "unit_price_minor": price})
    return normalised


def order_total(lines: Iterable[Mapping[str, Any]]) -> int:
    """Sum ``qty * unit_price_minor`` over normalised lines."""
    return sum(int(line["qty"]) * int(line["unit_price_minor"]) for line in lines)


def new_order(
    *,
    order_id: str,
    vendor: str,
    kind: str,
    lines: Iterable[Mapping[str, Any]],
    currency: str,
    clock: Clock,
    external_id: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Build a draft order record with its first history entry."""
    if kind not in ("parts", "pcb", "pcba"):
        raise ValueError(f"unsupported order kind {kind!r}")
    normalised = order_lines(lines)
    order: dict[str, Any] = {
        "id": order_id,
        "vendor": vendor,
        "kind": kind,
        "status": "draft",
        "lines": normalised,
        "total_minor": order_total(normalised),
        "currency": currency,
        "tracking": [],
        "history": [history_entry(clock, "draft", note)],
    }
    if external_id is not None:
        order["external_id"] = external_id
    return order


def find_order(
    orders: Iterable[Mapping[str, Any]],
    order_id: str,
) -> dict[str, Any] | None:
    """Return the order with ``order_id`` (as a mutable copy) or ``None``."""
    for order in orders:
        if order.get("id") == order_id:
            return dict(order)
    return None


def find_order_by_tracking(
    orders: Iterable[Mapping[str, Any]],
    tracking_number: str,
) -> dict[str, Any] | None:
    """Return the order whose ``tracking[].number`` matches, if any."""
    for order in orders:
        for tracking in order.get("tracking") or []:
            if isinstance(tracking, Mapping) and tracking.get("number") == tracking_number:
                return dict(order)
    return None


def next_order_id(orders: Iterable[Mapping[str, Any]], vendor: str) -> str:
    """Deterministic, collision-free draft order id for ``vendor``."""
    used = {str(order.get("id")) for order in orders}
    base = f"order:draft_{slugify(vendor)}"
    if base not in used:
        return base
    suffix = 2
    while f"{base}_{suffix}" in used:
        suffix += 1
    return f"{base}_{suffix}"
