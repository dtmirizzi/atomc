"""The ``plugin:orders`` implementation: cart building and a draft-only order ledger.

Honesty rules baked into this module:

* No tool ever places a real order or contacts a vendor. ``place`` writes a ``draft`` record and
  says so in its summary; every result carries ``real_order_placed=False`` and
  ``contacted_vendor=False``.
* The only carrier that ships is the mock carrier. ``poll``/``webhook`` label every result
  ``mock=True`` and refuse a non-mock carrier instead of pretending a real event arrived.
* IR writes go through the injected context, so the daemon enforces the plugin's ``/orders``
  write scope and revision/lock contract.
"""

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from atomc_core_ir import validate_ir_id

from .carriers import MOCK_CARRIER_NAME, Carrier, MockCarrier
from .carts import (
    CartFile,
    CartLine,
    cart_artifact_id,
    cart_lines_from_sourcing,
    group_by_vendor,
    render_cart,
)
from .clock import Clock, SystemClock, format_timestamp, parse_timestamp
from .errors import CartBuildError, IllegalTransitionError, LedgerError
from .ir import read_node, read_value
from .ledger import (
    ORDER_STATUSES,
    append_history,
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
from .manifest import PLUGIN_NAME, PLUGIN_VERSION, manifest_dict

__all__ = ["OrdersPlugin", "plugin"]

PLUGIN_ID = f"plugin:{PLUGIN_NAME}@{PLUGIN_VERSION}"
DRAFT_NOTICE = (
    "DRAFT ONLY: no order was placed and no vendor was contacted; a human must complete "
    "checkout with the vendor manually."
)


def _result(status_value: str, summary: str, **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": status_value,
        "summary": summary,
        "mock": False,
        "real_order_placed": False,
        "contacted_vendor": False,
    }
    result.update(extra)
    return result


def _artifact_root(ctx: Any) -> Path:
    root = getattr(ctx, "artifact_root", None)
    if callable(root):
        root = root()
    if root is None:
        return Path(tempfile.mkdtemp(prefix="atomc-orders-"))
    return Path(root)


def _write_cart_file(root: Path, cart_file: CartFile) -> tuple[Path, str, int]:
    destination = root / "orders" / cart_file.filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = cart_file.bytes
    destination.write_bytes(payload)
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    return destination, digest, len(payload)


def _cart_note(
    cart_file: CartFile,
    destination: Path,
    digest: str,
    artifact_id: str,
) -> str:
    return (
        f"cart artifact {artifact_id} format={cart_file.format} "
        f"path={destination} sha256={digest} lines={cart_file.line_count}. "
        f"{DRAFT_NOTICE}"
    )


def _to_order_lines(lines: list[CartLine]) -> list[dict[str, Any]]:
    return [
        {"sku": line.sku, "qty": line.qty, "unit_price_minor": line.unit_price_minor}
        for line in lines
        if line.sku
    ]


async def _load_orders(ctx: Any) -> tuple[int, bool, list[dict[str, Any]]]:
    rev, node = await read_node(ctx, "/orders")
    if node is None:
        return rev, False, []
    orders = node.get("orders") if isinstance(node, Mapping) else None
    if not isinstance(orders, list):
        raise LedgerError("IR /orders node is present but has no 'orders' list")
    return rev, True, [dict(order) for order in orders if isinstance(order, Mapping)]


async def _store_orders(
    ctx: Any,
    rev: int,
    present: bool,
    orders: list[dict[str, Any]],
) -> None:
    if not present:
        value = {"_meta": {"rev": 0, "lock": None}, "orders": orders}
        ops: list[dict[str, Any]] = [{"op": "add", "path": "", "value": value}]
    else:
        ops = [{"op": "add", "path": "/orders", "value": orders}]
    await ctx.ir_transact("/orders", rev, ops)


class OrdersPlugin:
    """Cart builder, draft-only order ledger and mock carrier tracking."""

    def __init__(self, *, clock: Clock | None = None, carrier: Carrier | None = None) -> None:
        self.manifest: dict[str, Any] = manifest_dict()
        self.clock: Clock = clock or SystemClock()
        self.carrier: Carrier = carrier or MockCarrier(self.clock)

    # -- tools --------------------------------------------------------------

    async def build_cart(self, ctx: Any, args: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Render per-vendor cart files and record draft ``/orders`` records."""
        options = args or {}
        dry_run = bool(options.get("dry_run"))
        kind = str(options.get("kind") or "parts")
        if kind not in ("parts", "pcb", "pcba"):
            return _result("FAIL", f"unsupported order kind {kind!r}")

        _, sourcing = await read_node(ctx, "/sourcing")
        if not isinstance(sourcing, Mapping):
            return _result(
                "FAIL",
                "IR has no /sourcing node; refresh sourcing before building a cart",
            )
        electrical = await read_value(ctx, "/electrical")
        build_qty = options.get("build_qty")
        try:
            cart_lines = cart_lines_from_sourcing(
                sourcing,
                electrical=electrical if isinstance(electrical, Mapping) else None,
                build_qty=int(build_qty) if build_qty is not None else None,
            )
        except (CartBuildError, ValueError) as exc:
            return _result(
                "FAIL",
                f"could not build cart from /sourcing: {exc}",
                suggestions=[{"message": "Choose one offer per BOM line, then retry build_cart."}],
            )

        grouped = group_by_vendor(cart_lines)
        currency = str(sourcing.get("currency") or "USD")
        root = _artifact_root(ctx)

        try:
            rev, present, orders = await _load_orders(ctx)
        except LedgerError as exc:
            return _result("FAIL", str(exc))
        updated_orders = list(orders)

        artifacts: list[dict[str, Any]] = []
        vendors: dict[str, Any] = {}
        order_ids: list[str] = []
        for vendor, vendor_lines in grouped.items():
            cart_file = render_cart(vendor, vendor_lines)
            destination = root / "orders" / cart_file.filename
            digest = "sha256:" + hashlib.sha256(cart_file.bytes).hexdigest()
            size = len(cart_file.bytes)
            if not dry_run:
                try:
                    destination, digest, size = _write_cart_file(root, cart_file)
                except OSError as exc:
                    return _result(
                        "FAIL",
                        f"could not write cart file for {vendor}: {exc}",
                        artifacts=artifacts,
                    )
            artifact_id = cart_artifact_id(vendor)
            artifacts.append(
                {
                    "id": artifact_id,
                    "kind": "csv",
                    "vendor": vendor,
                    "format": cart_file.format,
                    "path": str(destination),
                    "sha256": digest,
                    "bytes": size,
                    "written": not dry_run,
                }
            )
            vendors[vendor] = {
                "format": cart_file.format,
                "lines": cart_file.line_count,
                "file": cart_file.filename,
                "artifact": artifact_id,
            }
            if dry_run:
                continue

            lines = _to_order_lines(vendor_lines)
            note = _cart_note(cart_file, destination, digest, artifact_id)
            base_id = f"order:draft_{slugify(vendor)}"
            existing = find_order(updated_orders, base_id)
            if existing is not None and existing.get("status") == "draft":
                merged = dict(existing)
                merged["lines"] = order_lines(lines)
                merged["total_minor"] = order_total(lines)
                merged["currency"] = currency
                merged["kind"] = kind
                merged = append_history(merged, history_entry(self.clock, "draft", note))
                updated_orders = [
                    merged if order.get("id") == base_id else order for order in updated_orders
                ]
                order_ids.append(base_id)
            else:
                order_id = next_order_id(updated_orders, vendor)
                record = new_order(
                    order_id=order_id,
                    vendor=vendor,
                    kind=kind,
                    lines=lines,
                    currency=currency,
                    clock=self.clock,
                    note=note,
                )
                updated_orders.append(record)
                order_ids.append(order_id)

        if not dry_run:
            try:
                await _store_orders(ctx, rev, present, updated_orders)
            except Exception as exc:
                return _result(
                    "FAIL",
                    f"could not write /orders: {type(exc).__name__}: {exc}",
                    artifacts=artifacts,
                )

        total_lines = sum(len(item) for item in grouped.values())
        if dry_run:
            summary = (
                f"dry run: would write {len(grouped)} vendor cart(s) with {total_lines} line(s); "
                "nothing was written and no vendor was contacted"
            )
        else:
            summary = (
                f"built {len(grouped)} vendor cart(s) with {total_lines} line(s) and recorded "
                f"{len(order_ids)} DRAFT order(s); no vendor was contacted"
            )
        return _result(
            "PASS",
            summary,
            dry_run=dry_run,
            artifacts=artifacts,
            vendors=vendors,
            orders=order_ids,
            notice=DRAFT_NOTICE if not dry_run else None,
        )

    async def place(self, ctx: Any, args: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Record a DRAFT order for a human to place; never contacts a vendor."""
        options = args or {}
        vendor = str(options.get("vendor") or "").strip()
        if not vendor:
            return _result("FAIL", "place requires a non-empty 'vendor'")
        kind = str(options.get("kind") or "parts")
        if kind not in ("parts", "pcb", "pcba"):
            return _result("FAIL", f"unsupported order kind {kind!r}")

        _, sourcing = await read_node(ctx, "/sourcing")
        currency = (
            str(sourcing.get("currency") or "USD") if isinstance(sourcing, Mapping) else "USD"
        )

        raw_lines = options.get("lines")
        try:
            if raw_lines is not None:
                if not isinstance(raw_lines, list):
                    raise ValueError("'lines' must be a list")
                lines = order_lines(raw_lines)
            else:
                lines = await self._derive_vendor_lines(ctx, vendor, options)
        except (CartBuildError, ValueError) as exc:
            return _result("FAIL", f"could not prepare order lines: {exc}")

        try:
            rev, present, orders = await _load_orders(ctx)
        except LedgerError as exc:
            return _result("FAIL", str(exc))

        order_id = str(options.get("order_id") or next_order_id(orders, vendor))
        try:
            validate_ir_id(order_id)
        except ValueError as exc:
            return _result("FAIL", f"invalid order_id: {exc}")
        if find_order(orders, order_id) is not None:
            return _result("FAIL", f"order {order_id!r} already exists in /orders")

        note = str(options.get("note") or DRAFT_NOTICE)
        external_id = options.get("external_id")
        record = new_order(
            order_id=order_id,
            vendor=vendor,
            kind=kind,
            lines=lines,
            currency=currency,
            clock=self.clock,
            external_id=str(external_id) if external_id else None,
            note=note,
        )
        orders.append(record)
        try:
            await _store_orders(ctx, rev, present, orders)
        except Exception as exc:
            return _result("FAIL", f"could not write /orders: {type(exc).__name__}: {exc}")

        return _result(
            "PASS",
            f"recorded DRAFT order {order_id} for vendor {vendor!r}; {DRAFT_NOTICE}",
            mock=False,
            order_id=order_id,
            order_status="draft",
            vendor=vendor,
            lines=len(lines),
            total_minor=record["total_minor"],
            currency=currency,
            notice=DRAFT_NOTICE,
        )

    async def poll(self, ctx: Any, args: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Ask the configured carrier for tracking updates and apply them to ``/orders``."""
        options = args or {}
        carrier_name = str(options.get("carrier") or self.carrier.name)
        if carrier_name != self.carrier.name or not self.carrier.mock:
            return _result(
                "UNAVAILABLE",
                f"no carrier adapter named {carrier_name!r} ships; only the mock carrier is "
                "available",
                mock=True,
                carrier=MOCK_CARRIER_NAME,
            )

        try:
            rev, present, orders = await _load_orders(ctx)
        except LedgerError as exc:
            return _result("FAIL", str(exc))

        order_id = options.get("order_id")
        tracking_number = options.get("tracking_number")
        order: dict[str, Any] | None = None
        if order_id is not None:
            order = find_order(orders, str(order_id))
            if order is None:
                return _result("FAIL", f"order {order_id!r} was not found in /orders")
        if tracking_number is None and order is not None:
            tracking_number = self._first_tracking_number(order)
        if tracking_number is None and order is None:
            return _result(
                "FAIL",
                "poll requires 'order_id' or 'tracking_number'",
            )
        if tracking_number is None:
            return _result(
                "FAIL",
                f"order {order_id!r} has no tracking number; provide 'tracking_number'",
            )
        number = str(tracking_number)

        update = await self.carrier.track(number)
        if not update.found:
            return _result(
                "FAIL",
                update.message or f"mock carrier has no timeline for {number!r}",
                mock=True,
                carrier=update.carrier,
                tracking_number=number,
                events=[],
            )

        if order is None:
            order = find_order_by_tracking(orders, number)
        if order is None:
            return _result(
                "FAIL",
                f"no /orders record references tracking number {number!r}; "
                "record the order first so its history stays auditable",
                mock=True,
                carrier=update.carrier,
                tracking_number=number,
            )

        try:
            updated, applied = self._apply_timeline(order, update)
        except IllegalTransitionError as exc:
            return _result(
                "FAIL",
                str(exc),
                mock=True,
                carrier=update.carrier,
                tracking_number=number,
                order_id=order.get("id"),
            )

        events = [
            {"status": event.status, "at": format_timestamp(event.at), "note": event.note}
            for event in sorted(update.events, key=lambda item: item.at)
        ]
        if applied:
            orders = [
                updated if existing.get("id") == order.get("id") else existing
                for existing in orders
            ]
            try:
                await _store_orders(ctx, rev, present, orders)
            except Exception as exc:
                return _result("FAIL", f"could not write /orders: {type(exc).__name__}: {exc}")

        summary = (
            f"applied {applied} mock carrier event(s) for {number}; "
            "no real shipment data was fetched"
        )
        return _result(
            "PASS",
            summary,
            mock=True,
            carrier=update.carrier,
            tracking_number=number,
            order_id=order.get("id"),
            order_status=updated.get("status"),
            applied=applied,
            events=events,
        )

    async def webhook(self, ctx: Any, args: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Accept a mock carrier webhook payload; refuse anything that is not explicitly mock."""
        options = args or {}
        payload = options.get("payload")
        if not isinstance(payload, Mapping):
            return _result("FAIL", "webhook requires a 'payload' object")

        carrier = str(payload.get("carrier") or MOCK_CARRIER_NAME)
        is_mock = payload.get("mock") is True
        if carrier != MOCK_CARRIER_NAME or not is_mock:
            return _result(
                "FAIL",
                "webhook only accepts the mock carrier (carrier='mock' and mock=true); "
                "real carrier webhooks are not implemented",
                mock=True,
                carrier=MOCK_CARRIER_NAME,
            )

        tracking_number = payload.get("tracking_number")
        status = payload.get("status")
        if not tracking_number or not status:
            return _result("FAIL", "webhook payload requires 'tracking_number' and 'status'")
        number = str(tracking_number)
        target = str(status)
        if target not in ORDER_STATUSES:
            return _result(
                "FAIL",
                f"unknown status {target!r}; expected one of {', '.join(ORDER_STATUSES)}",
                mock=True,
                carrier=MOCK_CARRIER_NAME,
                tracking_number=number,
            )

        try:
            rev, present, orders = await _load_orders(ctx)
        except LedgerError as exc:
            return _result("FAIL", str(exc))

        order = find_order_by_tracking(orders, number)
        explicit_order_id = payload.get("order_id")
        if order is None and explicit_order_id:
            order = find_order(orders, str(explicit_order_id))
        if order is None:
            return _result(
                "FAIL",
                f"no /orders record references tracking number {number!r}",
                mock=True,
                carrier=MOCK_CARRIER_NAME,
                tracking_number=number,
            )

        raw_at = payload.get("at")
        try:
            event_at = parse_timestamp(str(raw_at)) if raw_at else self.clock.now()
        except ValueError as exc:
            return _result("FAIL", f"invalid webhook 'at': {exc}")
        note = str(payload.get("note") or "mock carrier webhook")

        if order.get("status") != target:
            try:
                validate_transition(str(order.get("status")), target)
            except IllegalTransitionError as exc:
                return _result(
                    "FAIL",
                    str(exc),
                    mock=True,
                    carrier=MOCK_CARRIER_NAME,
                    tracking_number=number,
                    order_id=order.get("id"),
                )

        updated = dict(order)
        tracking = list(updated.get("tracking") or [])
        entry: dict[str, Any] = {"carrier": MOCK_CARRIER_NAME, "number": number}
        url = payload.get("url")
        if url:
            entry["url"] = str(url)
        if not any(
            isinstance(item, Mapping)
            and item.get("number") == number
            and item.get("carrier") == MOCK_CARRIER_NAME
            for item in tracking
        ):
            tracking.append(entry)
        updated["tracking"] = tracking
        updated["status"] = target
        updated = append_history(
            updated,
            {
                "at": format_timestamp(event_at),
                "status": target,
                "note": f"{note} (mock carrier webhook; not a real carrier event)",
            },
        )
        orders = [
            updated if existing.get("id") == order.get("id") else existing for existing in orders
        ]
        try:
            await _store_orders(ctx, rev, present, orders)
        except Exception as exc:
            return _result("FAIL", f"could not write /orders: {type(exc).__name__}: {exc}")

        return _result(
            "PASS",
            f"recorded mock carrier webhook for {number}: {order.get('status')} -> {target}",
            mock=True,
            carrier=MOCK_CARRIER_NAME,
            tracking_number=number,
            order_id=order.get("id"),
            order_status=target,
            notice="MOCK carrier webhook only; no real carrier event was received.",
        )

    # -- internals ----------------------------------------------------------

    async def _derive_vendor_lines(
        self,
        ctx: Any,
        vendor: str,
        options: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        _, sourcing = await read_node(ctx, "/sourcing")
        if not isinstance(sourcing, Mapping):
            raise CartBuildError("IR has no /sourcing node; provide explicit 'lines' instead")
        electrical = await read_value(ctx, "/electrical")
        build_qty = options.get("build_qty")
        all_lines = cart_lines_from_sourcing(
            sourcing,
            electrical=electrical if isinstance(electrical, Mapping) else None,
            build_qty=int(build_qty) if build_qty is not None else None,
        )
        vendor_slug = slugify(vendor)
        selected = [line for line in all_lines if slugify(line.vendor) == vendor_slug]
        if not selected:
            raise CartBuildError(
                f"no chosen offers map to vendor {vendor!r}; pass explicit 'lines' or pick an offer"
            )
        return _to_order_lines(selected)

    def _first_tracking_number(self, order: Mapping[str, Any]) -> str | None:
        for tracking in order.get("tracking") or []:
            if isinstance(tracking, Mapping) and tracking.get("number"):
                return str(tracking["number"])
        external_id = order.get("external_id")
        return str(external_id) if external_id else None

    def _apply_timeline(
        self,
        order: Mapping[str, Any],
        update: Any,
    ) -> tuple[dict[str, Any], int]:
        updated = dict(order)
        tracking = [dict(item) for item in updated.get("tracking") or []]
        if not any(
            item.get("number") == update.number and item.get("carrier") == update.carrier
            for item in tracking
        ):
            tracking.append({"carrier": update.carrier, "number": update.number})
        updated["tracking"] = tracking

        existing_notes = {
            str(entry.get("note"))
            for entry in updated.get("history") or []
            if isinstance(entry, Mapping)
        }
        applied = 0
        for event in sorted(update.events, key=lambda item: item.at):
            note = f"mock carrier {update.number}: {event.note or event.status}"
            if note in existing_notes:
                continue
            current = str(updated.get("status"))
            if current != event.status:
                validate_transition(current, event.status)
                updated["status"] = event.status
            updated = append_history(
                updated,
                {
                    "at": format_timestamp(event.at),
                    "status": event.status,
                    "note": note,
                },
            )
            existing_notes.add(note)
            applied += 1
        return updated, applied


plugin = OrdersPlugin()

__all__ = ["DRAFT_NOTICE", "OrdersPlugin", "plugin"]
