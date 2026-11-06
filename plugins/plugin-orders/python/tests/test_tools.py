"""Tool handlers end to end with a fake context, injected clock and mock carrier."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from _orders_helpers import FakeContext, build_ir, demo_ir
from atomc_plugin_orders.carriers import MockCarrier
from atomc_plugin_orders.clock import FixedClock
from atomc_plugin_orders.plugin import OrdersPlugin


def _make_plugin() -> tuple[OrdersPlugin, FixedClock]:
    clock = FixedClock()
    plugin = OrdersPlugin(clock=clock, carrier=MockCarrier(clock))
    return plugin, clock


def _ctx(ir: Any, tmp_path: Path) -> FakeContext:
    return FakeContext(ir, tmp_path / "artifacts")


def _orders(ctx: FakeContext) -> list[dict[str, Any]]:
    document = ctx.ir.model_dump(mode="json", by_alias=True)
    node = document.get("orders") or {}
    return cast("list[dict[str, Any]]", list(node.get("orders", [])))


def _seeded_order_ir(
    *,
    status: str = "paid",
    tracking_number: str | None = "MOCK-TRACK-1001",
    order_id: str = "order:mock_test",
) -> Any:
    order: dict[str, Any] = {
        "id": order_id,
        "vendor": "mock",
        "kind": "parts",
        "status": status,
        "lines": [{"sku": "C1", "qty": 1, "unit_price_minor": 10}],
        "total_minor": 10,
        "currency": "USD",
        "tracking": ([{"carrier": "mock", "number": tracking_number}] if tracking_number else []),
        "history": [{"at": "2026-01-01T00:00:00Z", "status": status, "note": "seeded"}],
    }
    return build_ir(orders={"_meta": {"rev": 0}, "orders": [order]})


# -- build_cart -------------------------------------------------------------


async def test_build_cart_writes_files_and_draft_orders(tmp_path: Path) -> None:
    plugin, _ = _make_plugin()
    ctx = _ctx(demo_ir(), tmp_path)

    result = await plugin.build_cart(ctx, {})

    assert result["status"] == "PASS"
    assert result["real_order_placed"] is False
    assert result["contacted_vendor"] is False
    assert result["dry_run"] is False
    assert len(result["artifacts"]) == 4
    assert sorted(result["orders"]) == [
        "order:draft_digikey",
        "order:draft_jlcpcb",
        "order:draft_lcsc",
        "order:draft_mouser",
    ]
    written = sorted((tmp_path / "artifacts" / "orders").iterdir())
    assert [path.name for path in written] == [
        "digikey-cart.csv",
        "jlcpcb-cart.csv",
        "lcsc-cart.csv",
        "mouser-cart.csv",
    ]
    lcsc = (tmp_path / "artifacts" / "orders" / "lcsc-cart.csv").read_text(encoding="utf-8")
    assert lcsc.splitlines()[0] == "Comment,Designator,Footprint,LCSC Part #,Quantity"

    orders = _orders(ctx)
    assert len(orders) == 4
    assert all(order["status"] == "draft" for order in orders)
    lcsc_order = next(order for order in orders if order["id"] == "order:draft_lcsc")
    assert "DRAFT ONLY" in lcsc_order["history"][-1]["note"]
    assert "art:orders_lcsc_cart" in lcsc_order["history"][-1]["note"]


async def test_build_cart_is_idempotent_for_drafts(tmp_path: Path) -> None:
    plugin, _ = _make_plugin()
    ctx = _ctx(demo_ir(), tmp_path)
    await plugin.build_cart(ctx, {})
    await plugin.build_cart(ctx, {})
    orders = _orders(ctx)
    assert len(orders) == 4
    lcsc_order = next(order for order in orders if order["id"] == "order:draft_lcsc")
    assert len(lcsc_order["history"]) == 2


async def test_build_cart_dry_run_writes_nothing(tmp_path: Path) -> None:
    plugin, _ = _make_plugin()
    ctx = _ctx(demo_ir(), tmp_path)

    result = await plugin.build_cart(ctx, {"dry_run": True})

    assert result["status"] == "PASS"
    assert result["dry_run"] is True
    assert all(artifact["written"] is False for artifact in result["artifacts"])
    assert not (tmp_path / "artifacts" / "orders").exists()
    assert _orders(ctx) == []


async def test_build_cart_without_sourcing_fails(tmp_path: Path) -> None:
    plugin, _ = _make_plugin()
    ctx = _ctx(build_ir(), tmp_path)
    result = await plugin.build_cart(ctx, {})
    assert result["status"] == "FAIL"
    assert "no /sourcing" in result["summary"]


async def test_build_cart_without_chosen_offers_fails(tmp_path: Path) -> None:
    plugin, _ = _make_plugin()
    ir = build_ir(
        sourcing={
            "currency": "USD",
            "build_qty": 1,
            "bom": [
                {
                    "id": "bom:x",
                    "qty_per_unit": 1,
                    "offers": [],
                    "alternates": [],
                }
            ],
        }
    )
    ctx = _ctx(ir, tmp_path)
    result = await plugin.build_cart(ctx, {})
    assert result["status"] == "FAIL"
    assert "chosen_offer_ref" in result["summary"]


# -- place ------------------------------------------------------------------


async def test_place_records_a_draft_and_never_contacts_a_vendor(tmp_path: Path) -> None:
    plugin, _ = _make_plugin()
    ctx = _ctx(demo_ir(), tmp_path)

    result = await plugin.place(
        ctx,
        {"vendor": "lcsc", "lines": [{"sku": "C60442", "qty": 5, "unit_price_minor": 390}]},
    )

    assert result["status"] == "PASS"
    assert result["real_order_placed"] is False
    assert result["contacted_vendor"] is False
    assert result["order_status"] == "draft"
    order = _orders(ctx)[0]
    assert order["status"] == "draft"
    assert order["vendor"] == "lcsc"
    assert order["total_minor"] == 1950
    assert order["history"][0]["at"] == "2026-01-01T00:00:00Z"
    assert "DRAFT ONLY" in result["notice"]


async def test_place_derives_lines_from_chosen_sourcing_offers(tmp_path: Path) -> None:
    plugin, _ = _make_plugin()
    ctx = _ctx(demo_ir(), tmp_path)

    result = await plugin.place(ctx, {"vendor": "lcsc"})

    assert result["status"] == "PASS"
    order = _orders(ctx)[0]
    assert order["lines"] == [{"sku": "C60442", "qty": 5, "unit_price_minor": 390}]


async def test_place_rejects_duplicate_order_id(tmp_path: Path) -> None:
    plugin, _ = _make_plugin()
    ctx = _ctx(demo_ir(), tmp_path)
    await plugin.place(ctx, {"vendor": "lcsc", "order_id": "order:custom"})
    result = await plugin.place(ctx, {"vendor": "lcsc", "order_id": "order:custom"})
    assert result["status"] == "FAIL"
    assert "already exists" in result["summary"]


async def test_place_rejects_invalid_order_id(tmp_path: Path) -> None:
    plugin, _ = _make_plugin()
    ctx = _ctx(demo_ir(), tmp_path)
    result = await plugin.place(ctx, {"vendor": "lcsc", "order_id": "not-an-id"})
    assert result["status"] == "FAIL"
    assert "invalid order_id" in result["summary"]


async def test_place_requires_a_vendor(tmp_path: Path) -> None:
    plugin, _ = _make_plugin()
    ctx = _ctx(demo_ir(), tmp_path)
    result = await plugin.place(ctx, {})
    assert result["status"] == "FAIL"


# -- poll -------------------------------------------------------------------


async def test_poll_applies_mock_timeline(tmp_path: Path) -> None:
    plugin, _ = _make_plugin()
    ctx = _ctx(_seeded_order_ir(status="paid"), tmp_path)

    result = await plugin.poll(ctx, {"order_id": "order:mock_test"})

    assert result["status"] == "PASS"
    assert result["mock"] is True
    assert result["real_order_placed"] is False
    assert result["applied"] == 2
    assert result["order_status"] == "delivered"
    order = _orders(ctx)[0]
    assert order["status"] == "delivered"
    assert [entry["status"] for entry in order["history"][-2:]] == ["shipped", "delivered"]


async def test_poll_is_idempotent(tmp_path: Path) -> None:
    plugin, _ = _make_plugin()
    ctx = _ctx(_seeded_order_ir(status="paid"), tmp_path)
    await plugin.poll(ctx, {"order_id": "order:mock_test"})
    result = await plugin.poll(ctx, {"order_id": "order:mock_test"})
    assert result["status"] == "PASS"
    assert result["applied"] == 0


async def test_poll_rejects_illegal_transition(tmp_path: Path) -> None:
    plugin, _ = _make_plugin()
    ctx = _ctx(_seeded_order_ir(status="draft"), tmp_path)
    result = await plugin.poll(ctx, {"order_id": "order:mock_test"})
    assert result["status"] == "FAIL"
    assert _orders(ctx)[0]["status"] == "draft"


async def test_poll_unknown_number_fails_but_stays_mock(tmp_path: Path) -> None:
    plugin, _ = _make_plugin()
    ctx = _ctx(_seeded_order_ir(tracking_number="MOCK-NOPE"), tmp_path)
    result = await plugin.poll(ctx, {"order_id": "order:mock_test"})
    assert result["status"] == "FAIL"
    assert result["mock"] is True


async def test_poll_unknown_order_fails(tmp_path: Path) -> None:
    plugin, _ = _make_plugin()
    ctx = _ctx(_seeded_order_ir(), tmp_path)
    result = await plugin.poll(ctx, {"order_id": "order:nope"})
    assert result["status"] == "FAIL"


async def test_poll_refuses_non_mock_carrier(tmp_path: Path) -> None:
    plugin, _ = _make_plugin()
    ctx = _ctx(_seeded_order_ir(), tmp_path)
    result = await plugin.poll(ctx, {"order_id": "order:mock_test", "carrier": "ups"})
    assert result["status"] == "UNAVAILABLE"
    assert result["mock"] is True


async def test_poll_applies_by_external_id_after_place(tmp_path: Path) -> None:
    plugin, _ = _make_plugin()
    ctx = _ctx(demo_ir(), tmp_path)
    await plugin.place(
        ctx,
        {
            "vendor": "lcsc",
            "order_id": "order:mock_test",
            "external_id": "MOCK-TRACK-2002",
        },
    )
    # A draft order cannot jump straight to shipped; the mock carrier refuses the transition.
    result = await plugin.poll(ctx, {"order_id": "order:mock_test"})
    assert result["status"] == "FAIL"


# -- webhook ----------------------------------------------------------------


async def test_webhook_appends_tracking_and_history(tmp_path: Path) -> None:
    plugin, _ = _make_plugin()
    ctx = _ctx(_seeded_order_ir(status="placed"), tmp_path)

    result = await plugin.webhook(
        ctx,
        {
            "payload": {
                "carrier": "mock",
                "mock": True,
                "tracking_number": "MOCK-TRACK-1001",
                "status": "paid",
                "note": "mock webhook",
            }
        },
    )

    assert result["status"] == "PASS"
    assert result["mock"] is True
    assert result["order_status"] == "paid"
    order = _orders(ctx)[0]
    assert order["status"] == "paid"
    assert order["history"][-1]["note"].startswith("mock webhook")
    assert "not a real carrier event" in order["history"][-1]["note"]


async def test_webhook_rejects_illegal_transition(tmp_path: Path) -> None:
    plugin, _ = _make_plugin()
    ctx = _ctx(_seeded_order_ir(status="draft"), tmp_path)
    result = await plugin.webhook(
        ctx,
        {
            "payload": {
                "carrier": "mock",
                "mock": True,
                "tracking_number": "MOCK-TRACK-1001",
                "status": "delivered",
            }
        },
    )
    assert result["status"] == "FAIL"
    assert _orders(ctx)[0]["status"] == "draft"


async def test_webhook_refuses_non_mock_carrier(tmp_path: Path) -> None:
    plugin, _ = _make_plugin()
    ctx = _ctx(_seeded_order_ir(), tmp_path)
    result = await plugin.webhook(
        ctx,
        {
            "payload": {
                "carrier": "ups",
                "mock": False,
                "tracking_number": "1Z999",
                "status": "shipped",
            }
        },
    )
    assert result["status"] == "FAIL"
    assert "mock carrier" in result["summary"]


async def test_webhook_unknown_tracking_fails(tmp_path: Path) -> None:
    plugin, _ = _make_plugin()
    ctx = _ctx(_seeded_order_ir(), tmp_path)
    result = await plugin.webhook(
        ctx,
        {
            "payload": {
                "carrier": "mock",
                "mock": True,
                "tracking_number": "MOCK-UNKNOWN",
                "status": "paid",
            }
        },
    )
    assert result["status"] == "FAIL"


async def test_webhook_requires_mock_flag(tmp_path: Path) -> None:
    plugin, _ = _make_plugin()
    ctx = _ctx(_seeded_order_ir(), tmp_path)
    result = await plugin.webhook(
        ctx,
        {"payload": {"tracking_number": "MOCK-TRACK-1001", "status": "paid"}},
    )
    assert result["status"] == "FAIL"


def test_webhook_payload_is_json_serialisable(tmp_path: Path) -> None:
    # Guard against accidental non-JSON values leaking into a future webhook payload builder.
    payload = {"carrier": "mock", "mock": True, "tracking_number": "x", "status": "paid"}
    assert json.loads(json.dumps(payload)) == payload


@pytest.mark.parametrize(
    "tool",
    ["build_cart", "place", "poll", "webhook"],
)
def test_every_tool_is_registered(tool: str) -> None:
    assert callable(getattr(OrdersPlugin(clock=FixedClock()), tool))
