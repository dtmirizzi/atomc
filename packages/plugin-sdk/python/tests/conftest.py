"""Shared fixtures for the plugin SDK test suite.

The manifest JSON Schema is owned by WP-2.1 and lives at
``packages/plugin-sdk/schema/atomc-plugin.schema.json``. Tests always validate against that real
artifact — never a generated or copied substitute:

1. the canonical path (or ``ATOMC_PLUGIN_SCHEMA``) when present, else
2. the same file extracted from the WP-2.1 branch via ``git show`` into a temp path (isolated
   worktrees that have not merged WP-2.1 yet), else
3. a hard error telling the operator how to provide it.

Nothing here is committed and no second schema exists in the package.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest
from atomc_plugin_sdk.errors import SchemaNotFoundError
from atomc_plugin_sdk.schema import SCHEMA_RELATIVE_PATH, find_schema_path

_PREFERRED_REF = "origin/wp/2.1-plugin-sdk-ts"
_FALLBACK_REFS = ("wp/2.1-plugin-sdk-ts", "origin/main", "main")


def _repo_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / ".git").exists():
            return parent
    return None


def _schema_from_git() -> Path | None:
    root = _repo_root()
    if root is None:
        return None
    refs = [os.environ.get("ATOMC_PLUGIN_SCHEMA_REF", _PREFERRED_REF), *_FALLBACK_REFS]
    for ref in refs:
        if not ref:
            continue
        try:
            proc = subprocess.run(
                ["git", "-C", str(root), "show", f"{ref}:{SCHEMA_RELATIVE_PATH.as_posix()}"],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError, FileNotFoundError:
            continue
        if not proc.stdout.strip():
            continue
        tmp_dir = Path(tempfile.mkdtemp(prefix="atomc-plugin-schema-"))
        tmp_path = tmp_dir / "atomc-plugin.schema.json"
        tmp_path.write_text(proc.stdout, encoding="utf-8")
        os.environ["ATOMC_PLUGIN_SCHEMA"] = str(tmp_path)
        return tmp_path
    return None


def _bootstrap_schema() -> Path:
    existing = find_schema_path(required=False)
    if existing is not None:
        return existing
    fetched = _schema_from_git()
    if fetched is not None:
        return fetched
    raise SchemaNotFoundError(
        "the shared atomc plugin manifest schema was not found at "
        f"{SCHEMA_RELATIVE_PATH} and could not be extracted from the WP-2.1 git ref. Merge "
        "WP-2.1 or set ATOMC_PLUGIN_SCHEMA to the artifact before running these tests."
    )


SCHEMA_PATH = _bootstrap_schema()
USING_CANONICAL_SCHEMA = (
    SCHEMA_PATH.parts[-len(SCHEMA_RELATIVE_PATH.parts) :] == SCHEMA_RELATIVE_PATH.parts
)


VALID_MANIFEST: dict[str, Any] = {
    "manifest_version": "0.1.0",
    "name": "sourcing",
    "version": "0.1.0",
    "description": "BOM availability and cost sourcing",
    "atomc": ">=0.0.1 <0.2.0",
    "runtime": {"python": "atomc_plugin_sourcing:plugin", "ts": "./dist/index.js"},
    "watches": [
        {
            "id": "sourcing:bom-refresh",
            "ir": ["/electrical/components"],
            "files": ["**/*.ato"],
            "debounce_ms": 500,
        }
    ],
    "produces": ["/sourcing", "/fabrication"],
    "gates": [
        {
            "id": "gate:bom.all_in_stock",
            "severity": "blocking",
            "owner_agent": "ops-agent",
            "after": ["sourcing:bom-refresh"],
            "handler": "check_all_in_stock",
        }
    ],
    "tools": [
        {
            "name": "search_parts",
            "description": "Find purchasable alternates for a BOM line",
            "input_schema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "agents": ["ee-agent", "ops-agent"],
            "mutates": False,
            "handler": "search_parts",
        }
    ],
    "cli": [{"command": "quote", "description": "Refresh quotes", "handler": "quote"}],
    "ui": [{"panel": "bom", "title": "Bill of materials", "entry": "./dist/ui/bom.js"}],
}


@pytest.fixture
def valid_manifest() -> dict[str, Any]:
    return json.loads(json.dumps(VALID_MANIFEST))
