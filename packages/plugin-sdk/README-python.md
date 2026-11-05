# `atomc-plugin-sdk` (Python)

Author atomc plugins in Python. This package parses and validates the shared
`atomc-plugin.json` manifest, provides the runtime `PluginHost` protocol a plugin is handed by the
daemon, and ships conformance checks that prove a plugin implementation matches its manifest before
the daemon will load it.

It is the Python half of `packages/plugin-sdk`; the TypeScript half (`@atomc/plugin-sdk`) generates
the manifest JSON Schema that both SDKs validate against.

## Install

```bash
uv add atomc-plugin-sdk         # in a plugin project
# or, from the monorepo:
uv sync --all-packages
```

Requires Python 3.14, `pydantic>=2.14` and `jsonschema>=4.26`.

## Write a plugin

```python
# my_plugin/__init__.py
from atomc_plugin_sdk import PluginHost, atomc_plugin

MANIFEST = {
    "manifest_version": "0.1.0",
    "name": "sourcing",
    "version": "0.1.0",
    "description": "BOM availability and cost sourcing",
    "atomc": ">=0.0.1 <0.2.0",
    "runtime": {"python": "my_plugin:plugin"},
    "watches": [{"id": "sourcing:bom-refresh", "ir": ["/electrical/components"]}],
    "produces": ["/sourcing"],
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
            "input_schema": {"type": "object", "additionalProperties": False},
            "agents": ["ee-agent", "ops-agent"],
            "mutates": False,
            "handler": "search_parts",
        }
    ],
    "cli": [{"command": "quote", "description": "Refresh quotes", "handler": "quote"}],
    "ui": [],
}


@atomc_plugin(manifest=MANIFEST)
class Plugin:
    """Handler names must match the manifest's gate/tool/CLI handler fields."""

    def check_all_in_stock(self, host: PluginHost) -> None:
        snapshot = host.ir_get("/sourcing")
        # ... inspect snapshot.value, then:
        host.ir_transact("/sourcing", snapshot.rev, [
            {"op": "add", "path": "/last_check", "value": "ok"},
        ], holder="ops-agent")

    def search_parts(self, host: PluginHost, args: dict) -> dict:
        cached = host.cache.get("search_parts")
        if cached is not None:
            return cached
        result = {"offers": []}
        host.cache.set("search_parts", result, ttl_s=3600)
        return result

    def quote(self, host: PluginHost) -> None:
        host.events.emit("log", {"level": "info", "msg": "quotes refreshed"})


plugin = Plugin()
```

Decoration validates the manifest eagerly and attaches it as `__atomc_manifest__`; it does not
import or call the plugin body at import time. `@atomc_plugin` accepts a class, a factory function,
or an instance. Use `define_plugin(manifest, handlers={...})` when you prefer an explicit handler
registry (a `PluginDefinition`) over class methods.

### The `PluginHost` protocol

`PluginHost` is a structural protocol (no daemon dependency). The daemon provides it; tests can use
`atomc_plugin_sdk.testing.FakePluginHost`.

| Member | Purpose |
|--------|---------|
| `ir_get(path="/")` | read an IR subtree → `IrSnapshot(rev, value)` |
| `ir_transact(path, base_rev, ops, holder=None)` | apply RFC 6902 ops **relative to `path`** under optimistic concurrency → `TransactResult(new_rev, changed_paths)` |
| `artifact_root` | `Path` the plugin writes build artifacts into |
| `logger` | structured logger (`debug/info/warning/error`) |
| `cache` | namespaced `get/set(ttl_s=…)/delete` cache |
| `events.emit(topic, data)` | push best-effort notifications |

## Validate and check conformance

```python
from atomc_plugin_sdk import assert_conformance, conformance, load_manifest

manifest = load_manifest("atomc-plugin.json")   # path, dict, JSON text or bytes
report = conformance(plugin)                    # structured ConformanceReport
if not report.ok:
    for finding in report.errors:
        print(finding.code, finding.path, finding.message)

assert_conformance(plugin)                      # raises PluginConformanceError on failure
```

Conformance validates the manifest against the shared JSON Schema, re-applies the contract's
cross-field rules, and checks that every declared handler exists and is callable. When a plugin
exposes an explicit handler registry it also rejects handlers that are registered but not declared.
Errors carry a `code`, a JSON-pointer `path`, and a message.

## Manifest schema origin

The manifest JSON Schema is **generated from the TypeScript Zod schema** by WP-2.1 and committed at:

```
packages/plugin-sdk/schema/atomc-plugin.schema.json
```

This SDK validates raw documents against that exact artifact with Draft 2020-12 (`jsonschema`) and
**never ships a second, divergent schema**. Resolution order:

1. `ATOMC_PLUGIN_SCHEMA` environment variable (explicit file path), else
2. `packages/plugin-sdk/schema/atomc-plugin.schema.json` found by walking up from this package, else
3. a `_schema/atomc-plugin.schema.json` vendored next to the module (distribution builds only).

Keeping the TypeScript artifact authoritative means the two SDKs cannot drift: a change to the
manifest contract is made once in Zod, regenerated, and both SDKs pick it up.
