# WP-1.2 `core-ir-ts` — handoff

## What was built

`@atomc/core-ir` at `packages/core-ir/ts/` — the TypeScript half of the Unified System IR,
implementing `docs/architecture/contracts/ir-schema.md` §6.

- **Generated code** (`src/generated/`, committed, not hand-edited):
  - `types.ts` — TS interfaces via `json-schema-to-typescript` (root `SystemIR` + all `$defs`).
  - `zod.ts` — zod 4 runtime schemas via a hand-rolled JSON-Schema→zod emitter.
- **Public API** (`src/index.ts`):
  - `type SystemIR`
  - `SystemIRSchema` (typed `ZodType<SystemIR>`)
  - `parseSystemIR(json): SystemIR`
  - `SCHEMA_VERSION = "0.1.0"`
  - `type JsonPatchOp`, `patch(path): PatchBuilder` (add/remove/replace/move/copy/test/build)
  - `getAt<T>(ir, pointer)` plus RFC 6901 helpers (`parsePointer`, `joinPointer`, escaping)
- **Generator** (`scripts/gen.ts`): `pnpm gen` and `pnpm gen:check` (drift). Emits both files
  deterministically; `--schema <path>` overrides the source schema.
- **Tests** (`test/`): pointer/patch unit tests; schema tests; fixture validation (local fixtures +
  `packages/core-ir/fixtures/*.json` and `fixtures/invalid/*.json` when present); drift check.
  Coverage is 100% of `src/lib/**` (threshold 85%).
- Package `README.md`.

Generated files were produced from the **canonical** schema
(`packages/core-ir/schema/system_ir.schema.json`, git blob
`ad7b44ee6c3f03a246a9b33c0dac3ca3ca799263`), which is now merged into this branch (main merge
`0d3fbd4`). Regenerating at the default path is byte-identical to the committed output.

## How to verify

On the merged branch (canonical schema + fixtures present):

```bash
pnpm install --frozen-lockfile
pnpm --filter @atomc/core-ir gen:check    # byte-identical to committed generated output
pnpm --filter @atomc/core-ir test         # 34 tests: local + WP-1.1 fixtures + drift
pnpm --filter @atomc/core-ir test:coverage
pnpm --filter @atomc/core-ir typecheck
pnpm --filter @atomc/core-ir build        # ESM + CJS + .d.ts
pnpm --filter @atomc/core-ir lint
```

`packages/core-ir/fixtures/*.json` (atomc-pad, minimal) all parse; the six
`fixtures/invalid/*.json` are rejected by zod or by a documented Python-only semantic check. The
drift test compares against the canonical schema with no flags.

## Design decisions

- **Two-tool generation.** `json-schema-to-typescript` for types (mature, handles Pydantic output);
  a ~200-line hand-rolled emitter for zod because zod-4-specific codegen (`z.lazy` cycles, strict
  objects, discriminated/anyOf handling) from generic schema-to-zod tools was fragile. The emitter
  supports only the Pydantic v2 subset and **throws** on anything unknown rather than under-validating.
- **Every `$defs` entry is emitted as `z.lazy(() => …)`**, so ordering/recursion is a non-issue.
- **`anyOf` with `null` becomes `.nullable()`**; optional fields become `.optional()` or `.default(v)`
  when the schema carries a default, matching Pydantic serialization semantics.
- **Patch paths** are treated as already-escaped RFC 6901 fragments joined onto the builder base
  (`patch("/sourcing").add("bom/-", x)` → `/sourcing/bom/-`); callers escape literal `~`/`/` themselves.
- **Invalid-fixture handling** (brief item 4): zod covers structural errors. Unique ids, `_ref`
  integrity, and keyboard `row`/`col` bounds are Python-only in v0.1, so the test classifies an
  accepted invalid fixture against those documented semantic checks rather than failing blindly.

## Deviations from contract

None from `ir-schema.md` §6 — all five required exports exist and validate the real schema.

## Open issues

- The drift test still guards against the canonical schema being absent
  (`it.skipIf(!existsSync(REAL_SCHEMA))`) so the package can be developed standalone; on the merged
  branch it runs and passes.
- The invalid-fixture semantic classifier is intentionally minimal and lives in the test only. If
  WP-1.1 finalizes additional Python-only semantic checks, extend `classifyPythonOnly()`.
- `format: "date-time"` values are validated as plain strings by zod (shape-only); numeric/string
  bounds and `pattern` constraints are emitted into zod. Python owns strict timestamp/format checks.

## Root changes needed

- **`pnpm-lock.yaml` was updated** (new `packages/core-ir/ts` importer + catalog resolutions:
  zod, vitest, @vitest/coverage-v8, tsup, tsx, json-schema-to-typescript, @types/node, vite,
  typescript 5.9). This is committed on this branch; the orchestrator owns the root lockfile, so
  flagging it here.
- **Package-local `vite: "catalog:"` devDependency added.** After merging main, the VitePress docs
  package pulled `vite@5.4.21` into the shared store, which broke vitest 5 (`./module-runner` not
  exported). Pinning `vite` to the catalog (`^8.3.5`) for this package restores a working resolution.
  This is inside `packages/core-ir/ts/package.json` (owned path), but changes the root lockfile.
- No edits to `package.json`, `pnpm-workspace.yaml`, `turbo.json`, `biome.json`, or `tsconfig.base.json`
  were needed.
- Per PLAN §11, `packages/core-ir/ts` pins a package-local `typescript@^5.9.0` because `tsup`'s d.ts
  bundler requires the TypeScript compiler API, which TypeScript 7 no longer ships. The rest of the
  repo stays on TypeScript 7.
