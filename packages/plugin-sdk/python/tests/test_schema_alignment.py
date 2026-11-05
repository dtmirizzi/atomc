"""Parity between the Python SDK and the shared WP-2.1 JSON Schema.

These tests guard against the Python SDK inventing stricter (or looser) structural rules than the
TypeScript-generated schema. Edge cases below were previously over-restricted by hand-written
Python validators; they now defer to the shared schema.
"""

from __future__ import annotations

from typing import Any

import pytest
from atomc_plugin_sdk.errors import ManifestValidationError
from atomc_plugin_sdk.manifest import validate_manifest
from atomc_plugin_sdk.schema import validate_against_schema

_TOOL: dict[str, Any] = {
    "name": "search_parts",
    "description": "Find parts",
    "input_schema": {"type": "object"},
    "agents": ["ops-agent"],
    "mutates": False,
    "handler": "search_parts",
}

_GATE: dict[str, Any] = {
    "id": "gate:x",
    "severity": "blocking",
    "owner_agent": "ops-agent",
    "after": [],
    "handler": "check",
}


def _schema_accepts(data: dict[str, Any]) -> bool:
    return not validate_against_schema(data)


def _python_accepts(data: dict[str, Any]) -> bool:
    try:
        validate_manifest(data)
    except ManifestValidationError:
        return False
    return True


@pytest.mark.parametrize(
    ("label", "overrides"),
    [
        # The shared `name` pattern is ^[a-z0-9]+(?:-[a-z0-9]+)*$ and allows a leading digit and
        # a literal `plugin-` prefix (the contract prose says otherwise; see handoff open issues).
        ("name-leading-digit", {"name": "0plugin"}),
        ("name-plugin-prefix", {"name": "plugin-sourcing"}),
        # The shared SemVer pattern accepts a leading-zero prerelease identifier.
        ("semver-leading-zero-prerelease", {"version": "1.0.0-01"}),
        # runtime.python allows `$` in the attribute; runtime.ts must start with `./`.
        ("python-runtime-dollar-attr", {"runtime": {"python": "pkg.mod:plugin$"}}),
        ("ts-runtime-relative", {"runtime": {"ts": "./dist/index.js"}}),
        # A watch `ir` pointer may be the empty pointer (whole document).
        ("watch-empty-ir-pointer", {"watches": [{"id": "w:1", "ir": [""]}]}),
        # JSON Schema `true`/`false` are valid values for a tool input_schema.
        ("tool-input-schema-boolean", {"tools": [{**_TOOL, "input_schema": True}]}),
        # tool/cli/ui identifiers may contain underscores.
        ("tool-name-underscore", {"tools": [{**_TOOL, "name": "search_parts_v2"}]}),
    ],
)
def test_python_deferrs_to_schema_for_structural_rules(
    valid_manifest: dict[str, Any], label: str, overrides: dict[str, Any]
) -> None:
    data = {**valid_manifest, **overrides}
    assert _schema_accepts(data), f"{label}: shared schema unexpectedly rejected the manifest"
    assert _python_accepts(data), f"{label}: Python SDK rejected a schema-valid manifest"


@pytest.mark.parametrize(
    ("label", "overrides"),
    [
        ("bad-name", {"name": "Bad_Name"}),
        ("bad-semver", {"version": "one.two"}),
        ("bad-watch-pointer", {"watches": [{"id": "w:1", "ir": ["electrical"]}]}),
        ("bad-owner-agent", {"gates": [{**_GATE, "owner_agent": "nobody"}]}),
        ("forbidden-meta-scope", {"produces": ["/meta"]}),
        ("escaping-ui-entry", {"ui": [{"panel": "bom", "title": "B", "entry": "../b.js"}]}),
        ("unknown-key", {"unknown": 1}),
    ],
)
def test_python_rejects_what_the_schema_rejects(
    valid_manifest: dict[str, Any], label: str, overrides: dict[str, Any]
) -> None:
    data = {**valid_manifest, **overrides}
    assert not _schema_accepts(data), f"{label}: shared schema unexpectedly accepted the manifest"
    assert not _python_accepts(data), f"{label}: Python SDK accepted a schema-invalid manifest"
