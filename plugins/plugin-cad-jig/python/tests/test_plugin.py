"""Manifest, conformance and handler-wiring tests for the cad-jig plugin."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from atomc_plugin_cad_jig import MANIFEST, plugin
from atomc_plugin_sdk import conformance, validate_manifest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]

GATE_HANDLERS = {
    "check_plate_switch_cutouts",
    "check_case_usb_cutout_aligned",
    "check_pogo_spacing",
    "check_jig_no_collision",
    "check_enclosure_clearance",
}


def test_manifest_validates_against_shared_schema() -> None:
    validated = validate_manifest(
        json.loads((PLUGIN_ROOT / "atomc-plugin.json").read_text(encoding="utf-8"))
    )
    assert validated.name == "cad-jig"
    assert validated.produces == ["/mechanical"]


def test_declared_handlers_are_implemented() -> None:
    declared = set(MANIFEST.handler_names)
    assert declared == {
        *GATE_HANDLERS,
        "generate",
    }
    for name in declared:
        assert callable(getattr(plugin, name)), name


@pytest.mark.xfail(
    reason=(
        "plugin-sdk conformance() re-validates model_dump() which includes runtime.ts=None; "
        "the shared schema rejects the null (SDK bug, root change needed)"
    ),
    strict=False,
)
def test_sdk_conformance_passes() -> None:
    report = conformance(plugin)
    assert report.ok, report.errors


def test_manifest_declares_contract_surface() -> None:
    assert MANIFEST.name == "cad-jig"
    assert MANIFEST.runtime.python == "atomc_plugin_cad_jig:plugin"
    assert MANIFEST.produces == ["/mechanical"]
    assert {watch.id for watch in MANIFEST.watches} == {"cad:generate"}
    assert set(MANIFEST.watches[0].ir) == {"/mechanical", "/layout"}
    assert {gate.id for gate in MANIFEST.gates} == {
        "gate:mech.plate_switch_cutouts_14mm",
        "gate:mech.case_usb_cutout_aligned",
        "gate:mech.pogo_spacing_ge_2p54",
        "gate:mech.jig_no_collision",
        "gate:mech.enclosure_clearance",
    }
    assert {gate.handler for gate in MANIFEST.gates} == GATE_HANDLERS
    tool = MANIFEST.tools[0]
    assert tool.name == "generate"
    assert tool.mutates is True
    assert tool.handler == "generate"
    assert all(gate.after == ["cad:generate"] for gate in MANIFEST.gates)


def test_manifest_json_files_stay_in_sync() -> None:
    package_copy = (
        Path(__file__).resolve().parents[1] / "src" / "atomc_plugin_cad_jig" / "atomc-plugin.json"
    )
    root_copy = PLUGIN_ROOT / "atomc-plugin.json"
    assert json.loads(package_copy.read_text(encoding="utf-8")) == json.loads(
        root_copy.read_text(encoding="utf-8")
    )
    assert json.loads(package_copy.read_text(encoding="utf-8")) == MANIFEST.model_dump(
        mode="json", exclude_none=True
    )


async def test_gate_handlers_pass_on_fixture(ctx: Any) -> None:
    for handler in sorted(GATE_HANDLERS):
        result = await getattr(plugin, handler)(ctx)
        assert result["status"] == "PASS", (handler, result)


async def test_gate_handler_skips_when_ir_incomplete(ctx: Any) -> None:
    del ctx.ir["layout"]["outline"]
    result = await plugin.check_plate_switch_cutouts(ctx)
    assert result["status"] == "SKIP"
    assert "cannot derive the mechanical model" in result["summary"]


async def test_gate_handler_skips_without_layout(ctx: Any) -> None:
    del ctx.ir["layout"]
    result = await plugin.check_jig_no_collision(ctx)
    assert result["status"] == "SKIP"
    assert "/layout" in result["summary"]
