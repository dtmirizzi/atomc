"""Tool behavior: BOM lookup, refresh writes, cache provenance and honest failures."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from _sourcing_cassettes import cassette_transport
from _sourcing_helpers import FakeContext
from atomc_plugin_sourcing.adapters import build_adapters
from atomc_plugin_sourcing.adapters.base import VendorAdapter
from atomc_plugin_sourcing.cache import OfferCache
from atomc_plugin_sourcing.plugin import SourcingPlugin
from atomc_plugin_sourcing.service import SourcingService
from atomc_plugin_sourcing.tools import query_payload, refresh_payload
from conftest import FIXED_NOW_TEXT


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "examples" / "atomc-pad" / "system_ir.json"
        if candidate.is_file():
            return parent
    raise RuntimeError("could not locate repository root")


def example_sourcing() -> dict[str, Any]:
    document = json.loads(
        (_repo_root() / "examples" / "atomc-pad" / "system_ir.json").read_text(encoding="utf-8")
    )
    return copy.deepcopy(document["sourcing"])


def cassette_service(
    credentials: dict[str, dict[str, str]],
    fixed_clock: Callable[[], datetime],
) -> SourcingService:
    adapters: dict[str, VendorAdapter] = {}
    for vendor in ("lcsc", "mouser", "digikey", "nexar"):
        adapters[vendor] = build_adapters(
            env=credentials[vendor],
            transport=cassette_transport(vendor),
            clock=fixed_clock,
        )[vendor]
    return SourcingService(
        adapters,
        cache=OfferCache(ttl_s=24 * 60 * 60, clock=fixed_clock),
        clock=fixed_clock,
    )


def context_with_sourcing() -> FakeContext:
    return FakeContext(ir={"sourcing": example_sourcing()})


async def test_query_by_bom_line_id_returns_normalized_offers(
    credentials: dict[str, dict[str, str]],
    fixed_clock: Callable[[], datetime],
) -> None:
    service = cassette_service(credentials, fixed_clock)
    result = await query_payload(
        service,
        context_with_sourcing(),
        {"bom_line_id": "bom:U1", "vendors": ["lcsc"]},
    )
    assert result["status"] == "OK"
    assert result["available"] is True
    assert result["offers"][0]["id"] == "offer:bom_U1_lcsc_C60442"
    assert result["offers"][0]["vendor"] == "lcsc"
    assert result["offers"][0]["stock"] == 320
    assert result["offers"][0]["fetched_at"] == FIXED_NOW_TEXT
    assert result["offers"][0]["cached"] is False
    assert result["vendors"][0]["cached"] is False


async def test_query_by_mpn_and_cache_provenance(
    credentials: dict[str, dict[str, str]],
    fixed_clock: Callable[[], datetime],
) -> None:
    service = cassette_service(credentials, fixed_clock)
    args = {"mpn": "STM32F411CEU6", "vendors": ["mouser"]}
    first = await query_payload(service, FakeContext(ir={}), args)
    second = await query_payload(service, FakeContext(ir={}), args)
    assert first["status"] == "OK"
    assert first["offers"][0]["cached"] is False
    assert second["offers"][0]["cached"] is True
    assert second["offers"][0]["fetched_at"] == FIXED_NOW_TEXT
    assert "cache hit" in second["vendors"][0]["evidence"][0]["message"]


async def test_query_rejects_missing_identifiers_and_unknown_lines(
    credentials: dict[str, dict[str, str]],
    fixed_clock: Callable[[], datetime],
) -> None:
    service = cassette_service(credentials, fixed_clock)
    missing = await query_payload(service, FakeContext(ir={}), {})
    assert missing["status"] == "ERROR"
    assert missing["available"] is False
    unknown = await query_payload(service, context_with_sourcing(), {"bom_line_id": "bom:nope"})
    assert unknown["status"] == "ERROR"
    assert "not found" in unknown["summary"]


async def test_refresh_writes_only_sourcing_and_uses_real_cassette_data(
    credentials: dict[str, dict[str, str]],
    fixed_clock: Callable[[], datetime],
) -> None:
    service = cassette_service(credentials, fixed_clock)
    ctx = context_with_sourcing()
    result = await refresh_payload(service, ctx, {})

    assert result["status"] == "UPDATED"
    assert result["updated_lines"] == 3
    assert result["offers_written"] == 12
    assert len(ctx.transactions) == 1
    transaction = ctx.transactions[0]
    assert transaction["path"] == "/sourcing"
    assert transaction["base_rev"] == ctx.rev - 1
    assert all(op["path"].startswith("/bom/") for op in transaction["ops"])
    assert len(transaction["ops"]) == 6

    by_path = {op["path"]: op["value"] for op in transaction["ops"]}
    offers = by_path["/bom/0/offers"]
    assert len(offers) == 4
    assert {offer["vendor"] for offer in offers} == {"lcsc", "mouser", "digikey", "other"}
    assert len({offer["id"] for offer in offers}) == 4
    assert all(offer["fetched_at"] == FIXED_NOW_TEXT for offer in offers)
    # The old hand-written chosen ref no longer names a refreshed offer.
    assert by_path["/bom/0/chosen_offer_ref"] is None


async def test_refresh_without_sourcing_is_skip(
    credentials: dict[str, dict[str, str]],
    fixed_clock: Callable[[], datetime],
) -> None:
    service = cassette_service(credentials, fixed_clock)
    ctx = FakeContext(ir={})
    result = await refresh_payload(service, ctx, {})
    assert result["status"] == "SKIP"
    assert ctx.transactions == []


async def test_refresh_all_unavailable_leaves_ir_unchanged(
    fixed_clock: Callable[[], datetime],
) -> None:
    empty_adapters = {
        vendor: build_adapters(env={}, transport=cassette_transport(vendor), clock=fixed_clock)[
            vendor
        ]
        for vendor in ("lcsc", "mouser", "digikey", "nexar")
    }
    unavailable_service = SourcingService(empty_adapters, clock=fixed_clock)
    ctx = context_with_sourcing()
    result = await refresh_payload(
        unavailable_service,
        ctx,
        {"vendors": ["mouser", "digikey", "nexar"], "force": True},
    )
    assert result["status"] == "UNAVAILABLE"
    assert result["available"] is False
    assert "offers_written" not in result
    assert ctx.transactions == []


async def test_plugin_handlers_are_wired_to_the_service(
    credentials: dict[str, dict[str, str]],
    fixed_clock: Callable[[], datetime],
) -> None:
    service = cassette_service(credentials, fixed_clock)
    plugin = SourcingPlugin(service=service)
    result = await plugin.query_tool(
        context_with_sourcing(), {"bom_line_id": "bom:U2", "vendors": ["lcsc"]}
    )
    assert result["status"] == "OK"
    assert result["offers"][0]["sku"] == "C51118"
