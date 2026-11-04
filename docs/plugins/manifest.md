# Manifest reference

The plugin manifest `atomc-plugin.json` lives at a plugin package root. It is the only thing the
daemon needs to load a plugin. The normative schema is the
[plugin manifest contract](/architecture/contracts/plugin-manifest.md).

```jsonc
{
  "name": "plugin-sourcing",            // unique, kebab-case
  "version": "0.1.0",
  "description": "BOM sourcing and fab quotes",
  "atomc": ">=0.1 <0.2",                // compatible core range
  "runtime": {
    "python": "atomc_plugin_sourcing:plugin",
    "ts": "./dist/index.js"
  },
  "watches": [
    { "id": "bom-refresh", "ir": ["/electrical/components"], "files": ["**/*.ato"], "debounce_ms": 500 }
  ],
  "produces": ["/sourcing", "/fabrication"],
  "gates": [
    { "id": "gate:bom.all_in_stock", "severity": "blocking", "owner_agent": "ops-agent", "after": ["bom-refresh"] }
  ],
  "tools": [
    {
      "name": "search_parts",
      "description": "Search LCSC for a part by MPN.",
      "input_schema": { "type": "object" },
      "agents": ["ee-agent", "ops-agent"],
      "mutates": false
    }
  ],
  "cli": [{ "command": "quote", "description": "Fetch fab quotes", "handler": "quote" }],
  "ui": [{ "panel": "bom", "title": "BOM", "entry": "./dist/ui/bom.js" }]
}
```

## Fields

| Field | Required | Meaning |
| ----- | -------- | ------- |
| `name` | yes | Unique kebab-case plugin name |
| `version` | yes | Semver, lock-stepped with the monorepo |
| `description` | no | Human-readable summary |
| `atomc` | yes | Compatible `atomc` core version range |
| `runtime.python` | no* | `module:object` entrypoint |
| `runtime.ts` | no* | Path to the built ESM entrypoint |
| `watches[]` | no | DAG nodes this plugin reacts to |
| `produces[]` | no | IR subtrees this plugin may write |
| `gates[]` | no | Gates the plugin evaluates |
| `tools[]` | no | Tools exposed to swarm agents |
| `cli[]` | no | Commands contributed to the CLI |
| `ui[]` | no | Panels contributed to Studio |

\* At least one runtime entrypoint is required.

## How the DAG is built

Each `watches[].id` is a **DAG node**. Edges are inferred from `watches[].ir` pointers pointing at
another plugin's `produces`, and from `files` globs. `gates[].after` orders a gate after its
producing node.
