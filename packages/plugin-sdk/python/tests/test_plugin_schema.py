"""Schema location and shared-artifact behaviour."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from atomc_plugin_sdk.errors import ManifestError, SchemaNotFoundError
from atomc_plugin_sdk.schema import (
    SCHEMA_RELATIVE_PATH,
    find_schema_path,
    load_shared_schema,
    pointer_from_path,
    validate_against_schema,
)

SCHEMA_PATH = find_schema_path()
USING_CANONICAL_SCHEMA = (
    SCHEMA_PATH.parts[-len(SCHEMA_RELATIVE_PATH.parts) :] == SCHEMA_RELATIVE_PATH.parts
)


def test_schema_artifact_exists() -> None:
    assert SCHEMA_PATH.is_file()


def test_find_schema_path_matches_bootstrap() -> None:
    assert find_schema_path() == SCHEMA_PATH


def test_canonical_schema_layout_when_present() -> None:
    if USING_CANONICAL_SCHEMA:
        assert SCHEMA_PATH.parts[-len(SCHEMA_RELATIVE_PATH.parts) :] == SCHEMA_RELATIVE_PATH.parts
    else:  # pragma: no cover - only in an isolated WP-2.2 worktree
        assert Path(str(SCHEMA_PATH)).name == "atomc-plugin.schema.json"


def test_load_shared_schema_is_a_mapping() -> None:
    schema = load_shared_schema()
    assert isinstance(schema, dict)
    assert schema.get("$schema", "").endswith("2020-12/schema") or "properties" in schema


def test_pointer_from_path_escapes() -> None:
    assert pointer_from_path(()) == ""
    assert pointer_from_path(["a", 0, "b/c"]) == "/a/0/b~1c"
    assert pointer_from_path(["~tilde"]) == "/~0tilde"


def test_validate_against_schema_reports_unknown_top_level_key() -> None:
    errors = validate_against_schema({"manifest_version": "0.1.0", "bogus": True})
    assert errors
    assert all(isinstance(error, ManifestError) for error in errors)


def test_missing_schema_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ATOMC_PLUGIN_SCHEMA", str(tmp_path / "nope.json"))
    with pytest.raises(SchemaNotFoundError):
        find_schema_path()


def test_load_shared_schema_rejects_non_schema(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"type": "not-a-real-type"}), encoding="utf-8")
    with pytest.raises(SchemaNotFoundError):
        load_shared_schema(str(bad))
