"""``quote_pcb`` tool: spec resolution, IR writes and honest no-data paths."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from _sourcing_helpers import FakeContext
from atomc_plugin_sourcing.fab.jlcpcb import JlcpcbAdapter
from atomc_plugin_sourcing.fab.service import FabService
from atomc_plugin_sourcing.fab.spec import DEFAULT_PCB_SPEC
from atomc_plugin_sourcing.fab.tools import quote_pcb_payload
from test_fab._fab_cassettes import cassette_transport, static_transport

FAB_ENV: dict[str, str] = {"JLCPCB_APP_ID": "test-app", "JLCPCB_ACCESS_KEY": "test-key"}


def cassette_service(fixed_clock: Callable[[], datetime]) -> FabService:
    adapter = JlcpcbAdapter(
        transport=cassette_transport("jlcpcb"), env=dict(FAB_ENV), clock=fixed_clock
    )
    return FabService({"jlcpcb": adapter}, clock=fixed_clock)


def unavailable_service(fixed_clock: Callable[[], datetime]) -> FabService:
    adapter = JlcpcbAdapter(transport=static_transport({}), env={}, clock=fixed_clock)
    return FabService({"jlcpcb": adapter}, clock=fixed_clock)


def fab_context(ir: dict[str, Any] | None = None, *, rev: int = 0) -> FakeContext:
    return FakeContext(
        ir=ir if ir is not None else {},
        rev=rev,
        produces=("/sourcing", "/fabrication"),
    )


async def test_quote_pcb_creates_fabrication_node(
    fixed_clock: Callable[[], datetime],
) -> None:
    ctx = fab_context({}, rev=0)
    result = await quote_pcb_payload(cassette_service(fixed_clock), ctx, {"pcb": None})
    assert result["status"] == "UPDATED"
    assert result["quotes_written"] == 1
    assert result["new_rev"] == 1
    assert len(ctx.transactions) == 1
    transaction = ctx.transactions[0]
    assert transaction["path"] == "/fabrication"
    assert transaction["base_rev"] == 0
    assert len(transaction["ops"]) == 1
    op = transaction["ops"][0]
    assert op["op"] == "add"
    assert op["path"] == ""
    node = op["value"]
    assert node["pcb"]["layers"] == 2
    assert node["pcb"]["width_mm"] == 80.0
    assert node["pcb"]["qty"] == 5
    assert node["quotes"][0]["fab"] == "jlcpcb"
    assert node["quotes"][0]["id"].startswith("quote:jlcpcb_")


async def test_quote_pcb_derives_spec_from_ir_layout(
    fixed_clock: Callable[[], datetime],
) -> None:
    import json
    from pathlib import Path

    root = next(
        parent
        for parent in Path(__file__).resolve().parents
        if (parent / "examples" / "atomc-pad" / "system_ir.json").is_file()
    )
    document = json.loads((root / "examples" / "atomc-pad" / "system_ir.json").read_text())
    ctx = fab_context(document, rev=0)
    result = await quote_pcb_payload(cassette_service(fixed_clock), ctx, {})
    assert result["pcb"]["width_mm"] == 80.0
    assert result["pcb"]["qty"] == 5
    assert any("outline bbox" in item["message"] for item in result["evidence"])


async def test_quote_pcb_write_false_leaves_ir_untouched(
    fixed_clock: Callable[[], datetime],
) -> None:
    ctx = fab_context({}, rev=0)
    result = await quote_pcb_payload(
        cassette_service(fixed_clock), ctx, {"write": False, "pcb": None}
    )
    assert result["status"] == "OK"
    assert result["quotes_written"] == 0
    assert ctx.transactions == []


async def test_quote_pcb_no_data_is_unavailable_and_does_not_write(
    fixed_clock: Callable[[], datetime],
) -> None:
    ctx = fab_context({}, rev=0)
    result = await quote_pcb_payload(unavailable_service(fixed_clock), ctx, {"pcb": None})
    assert result["status"] == "UNAVAILABLE"
    assert result["quotes"] == []
    assert ctx.transactions == []


async def test_quote_pcb_merges_with_existing_quotes(
    fixed_clock: Callable[[], datetime],
) -> None:
    existing_quote = {
        "id": "quote:jlcpcb_othervendor",
        "fab": "jlcpcb",
        "total_minor": 9999,
        "currency": "USD",
        "lead_time_days": 10,
        "fetched_at": "2026-11-05T11:00:00Z",
        "breakdown": {"pcb": 9999},
        "url": None,
    }
    ir = {
        "fabrication": {
            "_meta": {"rev": 7, "lock": None},
            "pcb": DEFAULT_PCB_SPEC.model_dump(mode="json"),
            "quotes": [existing_quote],
        }
    }
    ctx = fab_context(ir, rev=7)
    result = await quote_pcb_payload(cassette_service(fixed_clock), ctx, {})
    assert result["status"] == "UPDATED"
    transaction = ctx.transactions[0]
    assert transaction["base_rev"] == 7
    quotes_op = next(op for op in transaction["ops"] if op["path"] == "/quotes")
    ids = [quote["id"] for quote in quotes_op["value"]]
    assert "quote:jlcpcb_othervendor" in ids
    assert len(ids) == 2
    pcb_op = next(op for op in transaction["ops"] if op["path"] == "/pcb")
    assert pcb_op["op"] == "replace"


async def test_quote_pcb_payload_spec_override(
    fixed_clock: Callable[[], datetime],
) -> None:
    ctx = fab_context({}, rev=0)
    result = await quote_pcb_payload(
        cassette_service(fixed_clock),
        ctx,
        {
            "pcb": {
                "layers": 2,
                "width_mm": 80.0,
                "height_mm": 80.0,
                "thickness_mm": 1.6,
                "finish": "HASL",
                "color": "green",
                "qty": 5,
            }
        },
    )
    assert result["status"] == "UPDATED"
    # The override matches the cassette's fixture spec, so a quote is fetched.
    assert result["quotes_written"] == 1


async def test_quote_pcb_rejects_invalid_payload(
    fixed_clock: Callable[[], datetime],
) -> None:
    ctx = fab_context({}, rev=0)
    result = await quote_pcb_payload(cassette_service(fixed_clock), ctx, {"fabs": ["pcbway"]})
    assert result["status"] == "ERROR"
    assert "unknown fab" in result["summary"]
    assert ctx.transactions == []


async def test_quote_pcb_rejects_invalid_pcb(
    fixed_clock: Callable[[], datetime],
) -> None:
    ctx = fab_context({}, rev=0)
    result = await quote_pcb_payload(cassette_service(fixed_clock), ctx, {"pcb": {"layers": 0}})
    assert result["status"] == "ERROR"
    assert "invalid 'pcb'" in result["summary"]
