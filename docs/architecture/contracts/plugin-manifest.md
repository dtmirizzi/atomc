# Contract: `atomc-plugin.json` (v0.1.0)

**Status: FROZEN for Phase 2.** This is the wire contract shared by the TypeScript SDK, Python SDK,
and daemon. Changes require orchestrator approval, edits here, and a manifest schema version bump.

## Conventions

- UTF-8 JSON; keys are `snake_case`; unknown keys are rejected (`additionalProperties: false`).
- `name` is the unique kebab-case distribution/plugin name without the `plugin-` prefix, e.g.
  `atopile`, `renode`, `cad-jig`, `sourcing`. Canonical IR plugin id is `plugin:<name>`.
- Plugin version is SemVer. `atomc` is a SemVer range for compatible core versions.
- JSON pointers use RFC 6901; plugin-produced paths must be top-level IR nodes or descendants.
- Handler strings are `module:attribute` for Python and module-relative export paths for TS.

## Manifest shape

```jsonc
{
  "manifest_version": "0.1.0",
  "name": "sourcing",
  "version": "0.1.0",
  "description": "BOM availability and cost sourcing",
  "atomc": ">=0.0.1 <0.2.0",
  "runtime": {
    "python": "atomc_plugin_sourcing:plugin",  // at least one runtime required
    "ts": "./dist/index.js"
  },
  "watches": [
    {
      "id": "sourcing:bom-refresh",           // globally unique DAG node id
      "ir": ["/electrical/components"],       // JSON pointers whose changes invalidate this node
      "files": ["**/*.ato"],                  // optional project-relative globs
      "debounce_ms": 500
    }
  ],
  "produces": ["/sourcing", "/fabrication"], // write permission scopes
  "gates": [
    {
      "id": "gate:bom.all_in_stock",
      "severity": "blocking",
      "owner_agent": "ops-agent",             // one of four specialists or null
      "after": ["sourcing:bom-refresh"],
      "handler": "check_all_in_stock"
    }
  ],
  "tools": [
    {
      "name": "search_parts",
      "description": "Find purchasable alternates for a BOM line",
      "input_schema": {"type": "object", "properties": {}, "additionalProperties": false},
      "agents": ["ee-agent", "ops-agent"],
      "mutates": false,
      "handler": "search_parts"
    }
  ],
  "cli": [
    {"command": "quote", "description": "Refresh BOM and fabrication quotes", "handler": "quote"}
  ],
  "ui": [
    {"panel": "bom", "title": "Bill of materials", "entry": "./dist/ui/bom.js"}
  ]
}
```

### Field rules

- Required top-level: `manifest_version`, `name`, `version`, `description`, `atomc`, `runtime`,
  `watches`, `produces`, `gates`, `tools`, `cli`, `ui`. Empty arrays are valid. At least one of
  `runtime.python` or `runtime.ts` is required.
- All module/handler references are validated syntactically at SDK load. Import/load is a separate
  daemon step whose errors are reported in `plugins.list`.
- `watches[].id` and `watches[].ir` are required; `files` defaults to `[]`, `debounce_ms` to `250`
  (integer, 0–60000). Watch ids are unique across loaded plugins.
- `produces` entries must be unique, valid JSON Pointers, and must begin with a valid top-level IR
  node (`/electrical`, `/layout`, `/keyboard`, `/firmware`, `/simulation`, `/mechanical`, `/sourcing`,
  `/fabrication`, `/orders`, `/gates`, `/provenance`, or `/ext`). `/meta` writes are forbidden.
- Gate `id` is globally unique and starts `gate:`; severity is `blocking|advisory`; owner is
  `ee-agent|fw-agent|mech-agent|ops-agent|null`; `after` references watch ids declared by this or
  another manifest; `handler` is a non-empty implementation export name.
- Tool names are unique within a plugin; `input_schema` is JSON Schema; `agents` is a subset of the
  four specialist names; `mutates` is boolean; mutating tools must declare `produces` scopes in the
  manifest; `handler` is a non-empty implementation export name.
- CLI command names are unique across loaded plugins and cannot shadow built-in `atomc` commands.
  `handler` is an implementation export name.
- UI `panel` ids are globally unique; `entry` is a package-relative path and must not escape the
  plugin root.

## Runtime registration API

- TS: `defineAtomcPlugin({ manifest, setup })` validates the manifest and returns an immutable
  `AtomcPlugin` descriptor. `setup(ctx)` may register gate/tool/cli handlers whose names match the
  manifest; undeclared handlers and missing implementations are conformance errors.
- Python: `@atomc_plugin(manifest=...)` decorates a plugin class/factory; the SDK validates the same
  manifest rules and exposes the manifest as `__atomc_manifest__`. A plugin instance implements the
  `AtomcPlugin` protocol and handlers by the declared names.
- Both SDKs provide `validate_manifest(data)` and `conformance(plugin)`; each built-in plugin must
  pass conformance tests before daemon registration.
- Manifest JSON Schema is generated from the TS Zod schema and committed at
  `packages/plugin-sdk/schema/atomc-plugin.schema.json`. The Python SDK validates the same JSON
  contract; it does not maintain a second independent schema.

## DAG and execution rules

Each `watches[].id` is a DAG node. Dependencies are derived from changed IR pointers matching a
watch's `ir` and plugin `produces`; `after` adds explicit dependency edges. File changes match
`files`. The daemon rejects cycles with a manifest-load error. A plugin may mutate only IR under its
`produces` scopes, and each transaction must still satisfy the core IR revision/lock contract.
