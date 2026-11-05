# @atomc/plugin-sdk

TypeScript plugin SDK for [atomc](../../README.md): the `atomc-plugin.json` manifest
schema, `defineAtomcPlugin()`, the change/watch matcher, and a conformance kit.

The manifest contract is **frozen at v0.1.0** in
[`docs/architecture/contracts/plugin-manifest.md`](../../docs/architecture/contracts/plugin-manifest.md).
The generated JSON Schema at
[`schema/atomc-plugin.schema.json`](./schema/atomc-plugin.schema.json) is the shared
cross-language data contract consumed by the Python SDK (`atomc-plugin-sdk`).

## Install (v0)

```bash
pnpm add @atomc/plugin-sdk
```

## Quick start

```ts
import { defineAtomcPlugin } from "@atomc/plugin-sdk";

export const plugin = await defineAtomcPlugin({
  manifest: {
    manifest_version: "0.1.0",
    name: "sourcing",
    version: "0.1.0",
    description: "BOM availability and cost sourcing",
    atomc: ">=0.0.1 <0.2.0",
    runtime: { python: "atomc_plugin_sourcing:plugin", ts: "./dist/index.js" },
    watches: [
      { id: "sourcing:bom-refresh", ir: ["/electrical/components"], files: ["**/*.ato"] },
    ],
    produces: ["/sourcing", "/fabrication"],
    gates: [
      {
        id: "gate:bom.all_in_stock",
        severity: "blocking",
        owner_agent: "ops-agent",
        after: ["sourcing:bom-refresh"],
        handler: "check_all_in_stock",
      },
    ],
    tools: [
      {
        name: "search_parts",
        description: "Find purchasable alternates for a BOM line",
        input_schema: {
          type: "object",
          properties: { mpn: { type: "string" } },
          required: ["mpn"],
          additionalProperties: false,
        },
        agents: ["ee-agent", "ops-agent"],
        mutates: false,
        handler: "search_parts",
      },
    ],
    cli: [{ command: "quote", description: "Refresh BOM and fabrication quotes", handler: "quote" }],
    ui: [{ panel: "bom", title: "Bill of materials", entry: "./dist/ui/bom.js" }],
  },
  setup(ctx) {
    ctx.registerGate("check_all_in_stock", async (context, gateId) => ({
      id: gateId,
      status: "PASS",
      severity: "blocking",
      plugin: "plugin:sourcing@0.1.0",
      owner_agent: "ops-agent",
      evaluated_at: new Date().toISOString(),
      ir_rev: 1,
      duration_ms: 1,
      summary: "all lines in stock",
      evidence: [],
      suggestions: [],
      refs: [],
    }));

    ctx.registerTool("search_parts", async (_context, args) => ({ query: args }));

    ctx.registerCli("quote", async () => ({ refreshed: true }));
  },
});
```

Handlers receive a [`PluginContext`](./ts/src/plugin.ts) at call time — it is a plain
interface (`ir`, `artifacts`, `logger`, `cache`, `signal`, `events`), so the SDK never
imports the daemon. `setup()` runs once when the plugin is defined; it must only
register handlers declared in the manifest. Nothing executes at module import time.

## Manifest fields

| Field | Notes |
| --- | --- |
| `manifest_version` | Always `"0.1.0"`. |
| `name` | kebab-case, no `plugin-` prefix; canonical id is `plugin:<name>`. |
| `version` | SemVer. |
| `atomc` | SemVer range of compatible core versions. |
| `runtime` | `{ python?: "module:attribute", ts?: "./dist/index.js" }`, at least one. |
| `watches[]` | `{ id, ir: [pointer], files?: [glob], debounce_ms? }` — DAG nodes. |
| `produces[]` | Write scopes; approved IR top-level nodes, never `/meta`. |
| `gates[]` | `{ id, severity, owner_agent, after, handler }`. |
| `tools[]` | `{ name, description, input_schema, agents, mutates, handler }`. |
| `cli[]` | `{ command, description, handler }`. |
| `ui[]` | `{ panel, title, entry }` — `entry` must not escape the package root. |

Defaults per the contract: `watches[].files` → `[]`, `watches[].debounce_ms` → `250`.
Unknown keys are rejected.

## Change matching

```ts
import { matchesGlob, pointerMatchesPattern, watchMatches } from "@atomc/plugin-sdk";

pointerMatchesPattern("/electrical/components", "/electrical/components/0/value"); // true (subtree)
pointerMatchesPattern("/a/*/c", "/a/b/c"); // true (single-segment `*`)
matchesGlob("**/*.ato", "boards/keeb/main.ato"); // true
```

Pointer matching is symmetric-subtree (a change is detected when either pointer is an
ancestor-or-equal of the other). `*` matches exactly one path segment. File globs are
anchored at the project root and normalized to POSIX; `**` matches zero or more segments.

## Conformance

```ts
import { assertConformance, validateToolInput } from "@atomc/plugin-sdk";

assertConformance(plugin); // throws PluginConformanceError on missing/undeclared handlers
const report = validateToolInput(plugin.manifest, "search_parts", { mpn: "STM32F411CEU6" });
```

`conformance()` also checks that tool input schemas compile (via `z.fromJSONSchema`) and
that mutating tools declare `produces` scopes. Deterministic scheduling (debounce, content
hashing) is daemon-owned.

## Schema generation

```bash
pnpm --filter @atomc/plugin-sdk schema:generate   # write schema/atomc-plugin.schema.json
pnpm --filter @atomc/plugin-sdk schema:check      # fail on drift (CI)
```

The generated JSON Schema encodes the structural contract (types, enums, patterns,
defaults, `additionalProperties: false`). Cross-field invariants that JSON Schema cannot
express (unique watch/gate/tool/panel ids, `after` reference integrity) are enforced by
the SDK validators in each language; `contract.test.ts` verifies the schema and the Zod
validator accept/reject the same fixtures.

## Scripts

| Script | Purpose |
| --- | --- |
| `build` | tsup → `dist/` (ESM + CJS + `.d.ts`). |
| `test` | Vitest suite. |
| `typecheck` | `tsc --noEmit`. |
| `lint` | Biome. |
| `schema:generate` / `schema:check` | Regenerate / drift-check the manifest JSON Schema. |
| `contract` | Schema/Zod parity tests. |

## License

Apache-2.0.
