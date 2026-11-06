"""Manifest validation, SDK conformance and daemon discovery."""

from __future__ import annotations

from pathlib import Path

import pytest
from atomc_plugin_atopile import plugin
from atomc_plugin_atopile.manifest import (
    conformant_manifest,
    load_plugin_manifest,
    manifest_dict,
    manifest_path,
)
from atomc_plugin_sdk import conformance, define_plugin, get_manifest

EXPECTED_GATES = {
    "gate:erc.no_unconnected",
    "gate:erc.assertions",
    "gate:layout.testpads.min_count",
    "gate:layout.testpads.nets_covered",
}
EXPECTED_TOOLS = {"compile", "import_pcb"}


def test_manifest_file_is_present() -> None:
    assert manifest_path().name == "atomc-plugin.json"
    assert manifest_path().is_file()


def test_manifest_parses_with_expected_declarations() -> None:
    manifest = load_plugin_manifest()
    assert manifest.name == "atopile"
    assert manifest.version == "0.1.0"
    assert {gate.id for gate in manifest.gates} == EXPECTED_GATES
    assert {tool.name for tool in manifest.tools} == EXPECTED_TOOLS
    assert manifest.produces == ["/electrical", "/layout"]
    assert {watch.id for watch in manifest.watches} == {"atopile:build"}


def test_conformance_accepts_plugin() -> None:
    manifest = conformant_manifest()
    handlers = {name: getattr(plugin, name) for name in manifest.handler_names}
    report = conformance(define_plugin(manifest, handlers=handlers))
    assert report.ok, report.findings


def test_all_declared_handlers_are_callable() -> None:
    manifest = load_plugin_manifest()
    for name in manifest.handler_names:
        assert callable(getattr(plugin, name))


def test_runtime_instance_exposes_plain_manifest_for_daemon() -> None:
    # See manifest.py: the daemon resolver needs a dict it can validate into its own model.
    assert get_manifest(plugin) is None
    assert isinstance(plugin.manifest, dict)
    assert plugin.manifest["name"] == "atopile"


def test_manifest_dict_matches_typed_manifest() -> None:
    raw = manifest_dict()
    typed = load_plugin_manifest()
    assert raw["name"] == typed.name
    assert raw["version"] == typed.version


def test_daemon_entry_point_discovery() -> None:
    atomcd = pytest.importorskip("atomcd")
    del atomcd
    import importlib.metadata as metadata

    from atomcd.plugins.discovery import discover_from_entry_points, discover_from_project

    entry_points = [
        entry for entry in metadata.entry_points(group="atomc.plugins") if entry.name == "atopile"
    ]
    loaded = discover_from_entry_points(entry_points)
    assert len(loaded) == 1
    assert loaded[0].name == "atopile"
    assert loaded[0].error is None
    assert loaded[0].plugin is not None

    project = discover_from_project(Path(__file__).resolve().parents[2])
    ours = [item for item in project if item.name == "atopile"]
    assert ours
    assert ours[0].error is None
