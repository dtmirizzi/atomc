"""The mutating ``optimize`` tool: selection writes, dry runs and honest failures."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from typing import Any

from _sourcing_helpers import FakeContext
from atomc_plugin_sourcing.optimizer.tools import optimize_payload
from helpers import add_offer, offer, pad_sourcing


def _ops_by_path(ctx: FakeContext) -> dict[str, Any]:
    transaction = ctx.transactions[-1]
    return {op["path"]: op["value"] for op in transaction["ops"]}


async def test_optimize_writes_chosen_offer_and_ranked_alternates() -> None:
    node = pad_sourcing()
    cheaper = offer(
        "offer:U2_mouser",
        vendor="mouser",
        stock=200,
        unit_price_minor=5,
        lead_time_days=5,
    )
    add_offer(node, "bom:U2", cheaper.model_dump(mode="json"))
    ctx = FakeContext(ir={"sourcing": node})

    result = await optimize_payload(ctx)

    assert result["status"] == "UPDATED"
    assert result["new_rev"] == ctx.rev
    assert result["selected_lines"] == 3
    assert result["total_extended_cost_minor"] == 2450
    ops = _ops_by_path(ctx)
    assert ops["/bom/1/chosen_offer_ref"] == "offer:U2_mouser"
    alternates = ops["/bom/1/alternates"]
    assert len(alternates) == 1
    assert "offer=offer:U2_lcsc" in alternates[0]["reason"]


async def test_optimize_dry_run_writes_nothing() -> None:
    node = pad_sourcing()
    ctx = FakeContext(ir={"sourcing": node})
    result = await optimize_payload(ctx, {"dry_run": True})
    assert result["status"] == "OK"
    assert result["dry_run"] is True
    assert ctx.transactions == []


async def test_optimize_writes_null_for_infeasible_line() -> None:
    node = pad_sourcing()
    for candidate in node["bom"][1]["offers"]:
        candidate["stock"] = 0
    ctx = FakeContext(ir={"sourcing": node})
    result = await optimize_payload(ctx)
    assert result["status"] == "UPDATED"
    assert result["infeasible_lines"] == 1
    line = next(item for item in result["lines"] if item["line"] == "bom:U2")
    assert line["feasible"] is False
    assert any("stock 0 below required quantity 5" in reason for reason in line["reasons"])
    ops = _ops_by_path(ctx)
    assert ops["/bom/1/chosen_offer_ref"] is None
    assert ops["/bom/1/alternates"] == []


async def test_optimize_skips_when_sourcing_is_absent() -> None:
    result = await optimize_payload(FakeContext(ir={}))
    assert result["status"] == "SKIP"


async def test_optimize_errors_on_invalid_constraints() -> None:
    node = pad_sourcing()
    result = await optimize_payload(FakeContext(ir={"sourcing": node}), {"constraints": {"x": 1}})
    assert result["status"] == "ERROR"
    assert "unknown constraint key" in result["summary"]


async def test_optimize_respects_vendor_count_cap_payload() -> None:
    node = pad_sourcing()
    add_offer(
        node,
        "bom:U1",
        offer("offer:U1_mouser", vendor="mouser", unit_price_minor=300).model_dump(mode="json"),
    )
    add_offer(
        node,
        "bom:U2",
        offer("offer:U2_mouser", vendor="mouser", unit_price_minor=5).model_dump(mode="json"),
    )
    add_offer(
        node,
        "bom:J1",
        offer("offer:J1_mouser", vendor="mouser", unit_price_minor=80).model_dump(mode="json"),
    )
    ctx = FakeContext(ir={"sourcing": node})
    result = await optimize_payload(ctx, {"constraints": {"vendor_count_cap": 1}})
    assert result["status"] == "UPDATED"
    assert result["distinct_vendors"] == ["mouser"]
    assert result["selected_lines"] == 3
