"""Manifest parsing, schema strictness and contract rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from atomc_plugin_sdk.errors import ManifestValidationError
from atomc_plugin_sdk.manifest import (
    MANIFEST_VERSION,
    PluginManifest,
    load_manifest,
    validate_manifest,
)


def _text(exc: ManifestValidationError) -> str:
    return " | ".join(f"{e.path}:{e.message}" for e in exc.errors)


def _paths(exc: ManifestValidationError) -> list[str]:
    return [e.path for e in exc.errors]


def test_valid_manifest_parses(valid_manifest: dict[str, Any]) -> None:
    manifest = validate_manifest(valid_manifest)
    assert isinstance(manifest, PluginManifest)
    assert manifest.manifest_version == MANIFEST_VERSION
    assert manifest.plugin_id == "plugin:sourcing"
    assert manifest.handler_names == ("check_all_in_stock", "search_parts", "quote")
    assert manifest.runtime.python == "atomc_plugin_sourcing:plugin"
    assert manifest.watches[0].debounce_ms == 500


def test_defaults_applied(valid_manifest: dict[str, Any]) -> None:
    valid_manifest["watches"] = [{"id": "w:1", "ir": ["/electrical"]}]
    manifest = validate_manifest(valid_manifest)
    assert manifest.watches[0].files == []
    assert manifest.watches[0].debounce_ms == 250


def test_missing_manifest_version() -> None:
    with pytest.raises(ManifestValidationError) as excinfo:
        validate_manifest({"name": "x"})
    assert "/manifest_version" in _paths(excinfo.value)
    assert "unsupported manifest_version" in _text(excinfo.value)


def test_unsupported_manifest_version(valid_manifest: dict[str, Any]) -> None:
    valid_manifest["manifest_version"] = "9.9.9"
    with pytest.raises(ManifestValidationError) as excinfo:
        validate_manifest(valid_manifest)
    assert "/manifest_version" in _paths(excinfo.value)
    assert "9.9.9" in _text(excinfo.value)


def test_unknown_key_rejected(valid_manifest: dict[str, Any]) -> None:
    valid_manifest["extra"] = True
    with pytest.raises(ManifestValidationError):
        validate_manifest(valid_manifest)


def test_missing_runtime(valid_manifest: dict[str, Any]) -> None:
    del valid_manifest["runtime"]
    with pytest.raises(ManifestValidationError) as excinfo:
        validate_manifest(valid_manifest)
    assert "runtime" in _text(excinfo.value)


def test_runtime_requires_at_least_one_entrypoint(valid_manifest: dict[str, Any]) -> None:
    valid_manifest["runtime"] = {}
    with pytest.raises(ManifestValidationError) as excinfo:
        validate_manifest(valid_manifest)
    assert "/runtime" in _paths(excinfo.value)


def test_python_runtime_must_be_module_attribute(valid_manifest: dict[str, Any]) -> None:
    valid_manifest["runtime"] = {"python": "not_a_module_attribute"}
    with pytest.raises(ManifestValidationError) as excinfo:
        validate_manifest(valid_manifest)
    assert any(path.startswith("/runtime") for path in _paths(excinfo.value))


def test_invalid_name(valid_manifest: dict[str, Any]) -> None:
    valid_manifest["name"] = "Plugin_Bad"
    with pytest.raises(ManifestValidationError) as excinfo:
        validate_manifest(valid_manifest)
    assert "/name" in _paths(excinfo.value)


def test_invalid_semver(valid_manifest: dict[str, Any]) -> None:
    valid_manifest["version"] = "one.two"
    with pytest.raises(ManifestValidationError) as excinfo:
        validate_manifest(valid_manifest)
    assert "/version" in _paths(excinfo.value)


@pytest.mark.parametrize("scope", ["/meta", "/nope", "sourcing", "/"])
def test_invalid_produces_scope(valid_manifest: dict[str, Any], scope: str) -> None:
    valid_manifest["produces"] = [scope]
    with pytest.raises(ManifestValidationError) as excinfo:
        validate_manifest(valid_manifest)
    assert "/produces/0" in _paths(excinfo.value)


def test_duplicate_produces(valid_manifest: dict[str, Any]) -> None:
    valid_manifest["produces"] = ["/sourcing", "/sourcing"]
    with pytest.raises(ManifestValidationError) as excinfo:
        validate_manifest(valid_manifest)
    assert "/produces/1" in _paths(excinfo.value)


def test_duplicate_watch_ids(valid_manifest: dict[str, Any]) -> None:
    valid_manifest["watches"].append({"id": "sourcing:bom-refresh", "ir": ["/layout"]})
    with pytest.raises(ManifestValidationError) as excinfo:
        validate_manifest(valid_manifest)
    assert "/watches/1" in _paths(excinfo.value)


def test_duplicate_gate_ids(valid_manifest: dict[str, Any]) -> None:
    valid_manifest["gates"].append(dict(valid_manifest["gates"][0]))
    with pytest.raises(ManifestValidationError):
        validate_manifest(valid_manifest)


def test_duplicate_tool_names(valid_manifest: dict[str, Any]) -> None:
    valid_manifest["tools"].append(dict(valid_manifest["tools"][0]))
    with pytest.raises(ManifestValidationError) as excinfo:
        validate_manifest(valid_manifest)
    assert "/tools/1" in _paths(excinfo.value)


def test_gate_id_must_start_with_gate(valid_manifest: dict[str, Any]) -> None:
    valid_manifest["gates"][0]["id"] = "bom.all_in_stock"
    with pytest.raises(ManifestValidationError) as excinfo:
        validate_manifest(valid_manifest)
    assert "/gates/0/id" in _paths(excinfo.value)


def test_watch_requires_ir(valid_manifest: dict[str, Any]) -> None:
    valid_manifest["watches"] = [{"id": "w:1"}]
    with pytest.raises(ManifestValidationError):
        validate_manifest(valid_manifest)


def test_watch_ir_must_be_pointer(valid_manifest: dict[str, Any]) -> None:
    valid_manifest["watches"] = [{"id": "w:1", "ir": ["electrical"]}]
    with pytest.raises(ManifestValidationError) as excinfo:
        validate_manifest(valid_manifest)
    assert "/watches/0/ir/0" in _paths(excinfo.value)


def test_debounce_bounds(valid_manifest: dict[str, Any]) -> None:
    valid_manifest["watches"][0]["debounce_ms"] = 70000
    with pytest.raises(ManifestValidationError):
        validate_manifest(valid_manifest)


def test_bad_agent_name(valid_manifest: dict[str, Any]) -> None:
    valid_manifest["tools"][0]["agents"] = ["not-an-agent"]
    with pytest.raises(ManifestValidationError):
        validate_manifest(valid_manifest)


def test_mutating_tool_requires_produces(valid_manifest: dict[str, Any]) -> None:
    valid_manifest["produces"] = []
    valid_manifest["tools"][0]["mutates"] = True
    with pytest.raises(ManifestValidationError) as excinfo:
        validate_manifest(valid_manifest)
    assert "/tools/0/mutates" in _paths(excinfo.value)


def test_ui_entry_cannot_escape(valid_manifest: dict[str, Any]) -> None:
    valid_manifest["ui"][0]["entry"] = "../outside.js"
    with pytest.raises(ManifestValidationError) as excinfo:
        validate_manifest(valid_manifest)
    assert "/ui/0/entry" in _paths(excinfo.value)


def test_empty_arrays_are_valid(valid_manifest: dict[str, Any]) -> None:
    valid_manifest.update({"watches": [], "gates": [], "tools": [], "cli": [], "ui": []})
    manifest = validate_manifest(valid_manifest)
    assert manifest.handler_names == ()


def test_load_manifest_from_mapping(valid_manifest: dict[str, Any]) -> None:
    assert load_manifest(valid_manifest).name == "sourcing"


def test_load_manifest_from_json_text(valid_manifest: dict[str, Any]) -> None:
    assert load_manifest(json.dumps(valid_manifest)).name == "sourcing"


def test_load_manifest_from_bytes(valid_manifest: dict[str, Any]) -> None:
    assert load_manifest(json.dumps(valid_manifest).encode()).name == "sourcing"


def test_load_manifest_from_path(valid_manifest: dict[str, Any], tmp_path: Path) -> None:
    path = tmp_path / "atomc-plugin.json"
    path.write_text(json.dumps(valid_manifest), encoding="utf-8")
    assert load_manifest(path).name == "sourcing"


def test_load_manifest_invalid_json() -> None:
    with pytest.raises(ManifestValidationError) as excinfo:
        load_manifest("{not json")
    assert "not valid JSON" in _text(excinfo.value)


def test_load_manifest_non_object_json() -> None:
    with pytest.raises(ManifestValidationError):
        load_manifest("[]")


def test_manifest_is_frozen(valid_manifest: dict[str, Any]) -> None:
    manifest = validate_manifest(valid_manifest)
    with pytest.raises((TypeError, ValueError)):
        manifest.name = "other"  # type: ignore[misc]


def test_errors_are_path_oriented(valid_manifest: dict[str, Any]) -> None:
    valid_manifest["gates"][0]["severity"] = "fatal"
    with pytest.raises(ManifestValidationError) as excinfo:
        validate_manifest(valid_manifest)
    assert all(isinstance(e.path, str) for e in excinfo.value.errors)
