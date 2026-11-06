# Writing a plugin

The plugin SDK (`defineAtomcPlugin` and the `PluginHost` protocol) is implemented in the TypeScript and Python packages. This page follows the [manifest contract](/architecture/contracts/plugin-manifest).

A plugin is a package with an `atomc-plugin.json` manifest at its root, plus a Python entrypoint
and/or a TypeScript entrypoint.

## TypeScript

```ts
import { defineAtomcPlugin } from "@atomc/plugin-sdk";

export default defineAtomcPlugin({
  name: "plugin-sourcing",
  watches: [{ id: "bom-refresh", ir: ["/electrical/components"], debounceMs: 500 }],
  produces: ["/sourcing", "/fabrication"],
  gates: [{ id: "gate:bom.all_in_stock", severity: "blocking", ownerAgent: "ops-agent" }],
  tools: [
    {
      name: "search_parts",
      description: "Search LCSC for a part by MPN.",
      inputSchema: { type: "object", properties: { mpn: { type: "string" } } },
      agents: ["ee-agent", "ops-agent"],
      mutates: false,
      handler: async (args, host) => {
        /* … */
      },
    },
  ],
});
```

## Python

```python
from atomc_plugin_sdk import atomc_plugin, PluginHost

@atomc_plugin(name="plugin-sourcing")
class SourcingPlugin:
    watches = [{"id": "bom-refresh", "ir": ["/electrical/components"]}]
    produces = ["/sourcing", "/fabrication"]

    def refresh_bom(self, host: PluginHost) -> None:
        components = host.ir.get("/electrical/components")
        # ... write back through host.ir.transact(...)
```

## What the host gives you

| Capability                         | Purpose                                                          |
| ---------------------------------- | ---------------------------------------------------------------- |
| `ir.get(path)`                     | Read a subtree at the current revision                           |
| `ir.transact(path, base_rev, ops)` | Write through a transaction, with conflict/lock semantics        |
| `artifacts`                        | A directory for this plugin's outputs, recorded in `/provenance` |
| `logger`                           | `structlog`-aware logger, surfaced over the `log` event topic    |
| `cache`                            | Content-addressed cache for expensive kernel calls               |

## Rules

- A plugin may only write the IR subtrees it lists in `produces`.
- Gates must be deterministic given `(IR rev, artifacts, cached external data)`.
- External calls must be cached with `fetched_at` so gates are reproducible offline.
- Register your package under the `atomc.plugins` entry point group, or ship an `atomc-plugin.json`
  the daemon can scan.

## Conformance

New plugin packages should add conformance tests using the SDK helpers; see [Conformance](/plugins/conformance).
