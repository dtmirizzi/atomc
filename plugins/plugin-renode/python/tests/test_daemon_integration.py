"""Integration with the daemon's plugin loader (project-tree manifest discovery).

The plugin is authored against the SDK and also ships an ``atomc-plugin.json`` that the daemon's
own parser consumes. This test proves the daemon can parse that manifest and resolve every declared
handler, including the DAG node handler.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from atomc_plugin_renode import manifest_path

atomcd_manifest = pytest.importorskip("atomcd.plugins.manifest")
atomcd_discovery = pytest.importorskip("atomcd.plugins.discovery")


def test_daemon_parses_manifest_and_resolves_handlers() -> None:
    manifest = atomcd_manifest.load_manifest(manifest_path())
    assert manifest.name == "renode"
    assert manifest.version == "0.1.0"
    assert sorted(g.id for g in manifest.gates) == [
        "gate:fw.matrix_scan",
        "gate:fw.renode_boot",
    ]
    assert [t.name for t in manifest.tools] == ["renode_generate"]
    assert manifest.produces == ["/simulation"]

    loaded = atomcd_discovery.load_plugin(
        manifest, source=str(manifest_path()), root=Path(manifest_path()).parent
    )
    assert loaded.loaded, loaded.error
    for gate in manifest.gates:
        assert callable(loaded.handler(gate.handler))
    for tool in manifest.tools:
        assert callable(loaded.handler(tool.handler))
    node_handlers = getattr(loaded.plugin, "__atomc_node_handlers__", {})
    assert "renode:generate" in node_handlers
