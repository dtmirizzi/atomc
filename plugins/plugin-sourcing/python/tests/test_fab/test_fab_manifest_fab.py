"""Manifest conformance for the fabrication gate, tool and watch."""

from __future__ import annotations

from atomc_plugin_sdk import conformance, define_plugin
from atomc_plugin_sourcing import plugin
from atomc_plugin_sourcing.manifest import conformant_manifest, load_plugin_manifest

FAB_TOOL = "quote_pcb"
FAB_GATE = "fab.quote_under_budget"
FAB_WATCH = "fab:quote"


def test_manifest_declares_fab_entries() -> None:
    manifest = load_plugin_manifest()
    assert FAB_TOOL in {tool.name for tool in manifest.tools}
    assert f"gate:{FAB_GATE}" in {gate.id for gate in manifest.gates}
    assert FAB_WATCH in {watch.id for watch in manifest.watches}
    assert "/fabrication" in manifest.produces
    assert "/sourcing" in manifest.produces


def test_fab_gate_has_ops_owner_and_handler() -> None:
    manifest = load_plugin_manifest()
    gate = next(gate for gate in manifest.gates if gate.id == f"gate:{FAB_GATE}")
    assert gate.owner_agent == "ops-agent"
    assert gate.severity == "blocking"
    assert gate.handler == "check_quote_under_budget"
    assert gate.after == [FAB_WATCH]


def test_fab_tool_is_mutating_and_ops_only() -> None:
    manifest = load_plugin_manifest()
    tool = next(tool for tool in manifest.tools if tool.name == FAB_TOOL)
    assert tool.mutates is True
    assert tool.agents == ["ops-agent"]
    assert tool.handler == "quote_pcb_tool"


def test_conformance_accepts_fab_handlers() -> None:
    manifest = conformant_manifest()
    handlers = {name: getattr(plugin, name) for name in manifest.handler_names}
    report = conformance(define_plugin(manifest, handlers=handlers))
    assert report.ok, report.findings
    assert callable(plugin.quote_pcb_tool)
    assert callable(plugin.check_quote_under_budget)
