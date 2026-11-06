"""End-to-end quote writing through the real daemon IR store (no network)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest
from atomc_core_ir import SystemIR
from atomc_plugin_sourcing.fab.jlcpcb import JlcpcbAdapter
from atomc_plugin_sourcing.fab.service import FabService
from atomc_plugin_sourcing.fab.tools import quote_pcb_payload
from test_fab._fab_cassettes import cassette_transport

pytest.importorskip("atomcd")

from atomcd.ir_store import IRStore
from atomcd.plugins.context import PluginContext

FAB_ENV: dict[str, str] = {"JLCPCB_APP_ID": "test-app", "JLCPCB_ACCESS_KEY": "test-key"}


def cassette_service(fixed_clock: Callable[[], datetime]) -> FabService:
    adapter = JlcpcbAdapter(
        transport=cassette_transport("jlcpcb"), env=dict(FAB_ENV), clock=fixed_clock
    )
    return FabService({"jlcpcb": adapter}, clock=fixed_clock)


def real_context(tmp_path: Path) -> PluginContext:
    store = IRStore(tmp_path)
    store.load()
    return PluginContext(
        plugin_name="sourcing",
        holder="agent:ops-agent#1",
        store=store,
        produces=["/sourcing", "/fabrication"],
        artifact_root=tmp_path / "artifacts",
        cache={},
    )


async def test_quote_pcb_creates_fabrication_node_in_real_store(
    tmp_path: Path, fixed_clock: Callable[[], datetime]
) -> None:
    ctx = real_context(tmp_path)
    result = await quote_pcb_payload(cassette_service(fixed_clock), ctx, {"pcb": None})
    assert result["status"] == "UPDATED"
    rev, fabrication = ctx.store.read("/fabrication")
    assert rev == 1
    assert fabrication["pcb"]["layers"] == 2
    assert fabrication["quotes"][0]["fab"] == "jlcpcb"
    # The persisted document still validates with the created node.
    SystemIR.load(ctx.store.path)


async def test_quote_pcb_merges_into_existing_fabrication_node(
    tmp_path: Path, fixed_clock: Callable[[], datetime]
) -> None:
    ctx = real_context(tmp_path)
    await quote_pcb_payload(cassette_service(fixed_clock), ctx, {"pcb": None})
    result = await quote_pcb_payload(cassette_service(fixed_clock), ctx, {"pcb": None})
    assert result["status"] == "UPDATED"
    _rev, fabrication = ctx.store.read("/fabrication")
    assert len(fabrication["quotes"]) == 1
