# @atomc/core-ir (TypeScript)

TypeScript types, [zod 4](https://zod.dev) runtime schemas, and JSON-Patch helpers for `system_ir.json`,
the unified hardware IR defined by `docs/architecture/contracts/ir-schema.md`.

The types and `SystemIRSchema` are **generated** from the JSON Schema emitted by the Python package
`atomc-core-ir` (`packages/core-ir/schema/system_ir.schema.json`). Do not edit `src/generated/**`
by hand.

## Usage

```ts
import { parseSystemIR, patch, getAt, SCHEMA_VERSION } from "@atomc/core-ir";

const ir = parseSystemIR(JSON.parse(await readFile("system_ir.json", "utf8")));
const ops = patch("/sourcing").add("bom/-", line).replace("build_qty", 5).build();
const rev = getAt<number>(ir, "/electrical/_meta/rev");
```

## Scripts

| Script | Purpose |
| --- | --- |
| `pnpm gen` | Regenerate `src/generated/types.ts` + `zod.ts`. Falls back to `test/stub.schema.json` when the canonical schema is not present (standalone checkout). |
| `pnpm gen:check` | Fail if committed generated output is stale (drift). |
| `pnpm test` | Vitest: schema validation of fixtures, pointer/patch unit tests, drift check. |
| `pnpm test:coverage` | Same with ≥85% coverage thresholds. |
| `pnpm typecheck` | `tsc --noEmit`. |
| `pnpm build` | tsup → `dist/` (ESM + CJS + `.d.ts`). |

## Design notes

- **Generation approach:** TypeScript types come from `json-schema-to-typescript`; zod schemas come
  from a small hand-rolled JSON-Schema→zod emitter in `scripts/gen.ts`. Only the subset Pydantic v2
  emits is supported (`$defs`/`$ref`, strict objects, enums/literals, `anyOf`-nullable, arrays,
  numeric/string bounds, patterns, `allOf`); anything else throws instead of silently mis-validating.
- **Referential integrity and cross-field semantics** (unique ids, `_ref` targets, keyboard
  `row`/`col` bounds) are validated by the Python loader only in v0.1; zod checks shape.
- The package pins `typescript@^5.9` locally because `tsup`'s d.ts bundler needs the TypeScript
  compiler API, which TypeScript 7 does not ship (PLAN §11 escape hatch).
