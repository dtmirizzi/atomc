# Contract: Plugin manifest `atomc-plugin.json` (v0.1) — draft, frozen at Phase 2 start

```jsonc
{
  "name": "plugin-sourcing",            // unique, kebab-case
  "version": "0.1.0",
  "description": "…",
  "atomc": ">=0.1 <0.2",                // compatible core range
  "runtime": { "python": "atomc_plugin_sourcing:plugin", "ts"?: "./dist/index.js" },
  "watches": [ { "id": "bom-refresh", "ir": ["/electrical/components"], "files"?: ["**/*.ato"], "debounce_ms": 500 } ],
  "produces": ["/sourcing", "/fabrication"],   // IR subtrees this plugin may write
  "gates": [ { "id": "gate:bom.all_in_stock", "severity": "blocking", "owner_agent": "ops-agent", "after": ["bom-refresh"] } ],
  "tools": [ { "name": "search_parts", "description": "…", "input_schema": {JSON Schema}, "agents": ["ee-agent","ops-agent"], "mutates": false } ],
  "cli":  [ { "command": "quote", "description": "…", "handler": "quote" } ],
  "ui":   [ { "panel": "bom", "title": "BOM", "entry": "./dist/ui/bom.js" } ]
}
```
DAG: each `watches[].id` is a DAG node; edges come from `ir` pointers ↔ other plugins' `produces`.
