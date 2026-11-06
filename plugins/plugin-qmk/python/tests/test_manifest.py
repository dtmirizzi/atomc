from __future__ import annotations

import json
from pathlib import Path

from atomc_plugin_qmk.manifest import MANIFEST
from atomc_plugin_qmk.plugin import plugin
from atomc_plugin_sdk import assert_conformance, load_manifest


def _plugin_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "atomc-plugin.json"
        if candidate.is_file():
            return parent
    raise RuntimeError("could not locate atomc-plugin.json")


def test_json_manifest_matches_python_manifest() -> None:
    root = _plugin_root()
    raw = json.loads((root / "atomc-plugin.json").read_text(encoding="utf-8"))
    assert raw == MANIFEST


def test_manifest_validates_with_shared_schema() -> None:
    root = _plugin_root()
    manifest = load_manifest(root / "atomc-plugin.json")
    assert manifest.name == "qmk"
    assert manifest.version == "0.1.0"
    assert [gate.id for gate in manifest.gates] == [
        "gate:fw.matrix_pins_match_ir",
        "gate:fw.qmk_compile",
    ]
    assert [tool.name for tool in manifest.tools] == ["qmk_generate", "qmk_compile"]
    assert manifest.produces == ["/firmware"]
    assert {watch.id for watch in manifest.watches} == {"qmk:keyboard", "qmk:firmware"}


def test_plugin_passes_sdk_conformance() -> None:
    manifest = assert_conformance(plugin)
    assert manifest.name == "qmk"


def test_plugin_exposes_declared_handlers() -> None:
    manifest = assert_conformance(plugin)
    for name in manifest.handler_names:
        assert callable(getattr(plugin, name, None))
