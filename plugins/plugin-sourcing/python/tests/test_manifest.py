"""Manifest validation, SDK conformance and daemon discovery."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path

import pytest
from atomc_plugin_sdk import conformance, define_plugin, get_manifest
from atomc_plugin_sourcing import plugin
from atomc_plugin_sourcing.manifest import (
    conformant_manifest,
    load_plugin_manifest,
    manifest_dict,
    manifest_path,
)

EXPECTED_TOOLS = {"query", "refresh"}


def test_manifest_file_is_present() -> None:
    assert manifest_path().name == "atomc-plugin.json"
    assert manifest_path().is_file()


def test_manifest_parses_with_expected_declarations() -> None:
    manifest = load_plugin_manifest()
    assert manifest.name == "sourcing"
    assert manifest.version == "0.1.0"
    # Other Phase-5 work packages (WP-5.2 optimizer, WP-5.3 fab quotes) extend the same manifest,
    # so the WP-5.1 tools are required members, not the whole set.
    assert {tool.name for tool in manifest.tools} >= EXPECTED_TOOLS
    assert "/sourcing" in manifest.produces
    assert "sourcing:refresh" in {watch.id for watch in manifest.watches}


def test_mutating_refresh_declares_sourcing_scope() -> None:
    manifest = load_plugin_manifest()
    refresh = next(tool for tool in manifest.tools if tool.name == "refresh")
    query = next(tool for tool in manifest.tools if tool.name == "query")
    assert refresh.mutates is True
    assert query.mutates is False
    assert refresh.agents == ["ee-agent", "ops-agent"]
    assert "/sourcing" in manifest.produces


def test_conformance_accepts_plugin_and_all_handlers_are_callable() -> None:
    manifest = conformant_manifest()
    handlers = {name: getattr(plugin, name) for name in manifest.handler_names}
    report = conformance(define_plugin(manifest, handlers=handlers))
    assert report.ok, report.findings
    for name in manifest.handler_names:
        assert callable(getattr(plugin, name))


def test_runtime_instance_exposes_plain_manifest_for_daemon() -> None:
    assert get_manifest(plugin) is None
    assert isinstance(plugin.manifest, dict)
    assert plugin.manifest["name"] == "sourcing"


def test_manifest_dict_matches_typed_manifest() -> None:
    raw = manifest_dict()
    typed = load_plugin_manifest()
    assert raw["name"] == typed.name
    assert raw["version"] == typed.version


def test_daemon_entry_point_discovery() -> None:
    pytest.importorskip("atomcd")
    from atomcd.plugins.discovery import discover_from_entry_points, discover_from_project

    entry_points = [
        entry
        for entry in importlib.metadata.entry_points(group="atomc.plugins")
        if entry.name == "sourcing"
    ]
    loaded = discover_from_entry_points(entry_points)
    assert len(loaded) == 1
    assert loaded[0].name == "sourcing"
    assert loaded[0].error is None
    assert loaded[0].plugin is not None

    project = discover_from_project(Path(__file__).resolve().parents[2])
    ours = [item for item in project if item.name == "sourcing"]
    assert ours
    assert ours[0].error is None
