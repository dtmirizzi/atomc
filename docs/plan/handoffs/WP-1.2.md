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

Generated files were produced from WP-1.1's **real** schema
(`origin/wp/1.1-core-ir-py:packages/core-ir/schema/system_ir.schema.json`, git blob
`ad7b44ee6c3f03a246a9b33c0dac3ca3ca799263`), so they match what lands upstream.

## How to verify

Standalone on this branch (canonical schema not yet merged, generator falls back to the stub):

```bash
pnpm install
pnpm --filter @atomc/core-ir gen          # uses stub fallback here
pnpm --filter @atomc/core-ir test
pnpm --filter @atomc/core-ir typecheck
pnpm --filter @atomc/core-ir build        # ESM + CJS + .d.ts
pnpm --filter @atomc/core-ir lint
```

Against WP-1.1's real schema (what I ran; equivalent once both branches merge):

```bash
SCHEMA=../wp-1-1-core-ir-py/packages/core-ir/schema/system_ir.schema.json
pnpm --filter @atomc/core-ir exec tsx scripts/gen.ts --schema "$SCHEMA"
pnpm --filter @atomc/core-ir exec tsx scripts/gen.ts --check --schema "$SCHEMA"
pnpm --filter @atomc/core-ir test        # 33 tests pass when WP-1.1 fixtures are linked in
pnpm --filter @atomc/core-ir typecheck
pnpm --filter @atomc/core-ir build
```

After both branches merge, `packages/core-ir/schema/system_ir.schema.json` exists at the default
path and `pnpm --filter @atomc/core-ir gen` / `gen:check` / `test` (drift test un-skips) run against it
with no flags.

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

- The drift test is **skipped** when `packages/core-ir/schema/system_ir.schema.json` is absent (the
  standalone-branch case). It un-skips automatically once WP-1.1's schema lands on the branch.
- The invalid-fixture semantic classifier is intentionally minimal and lives in the test only. If
  WP-1.1 finalizes additional Python-only semantic checks, extend `classifyPythonOnly()`.
- `format: "date-time"` values are validated as plain strings by zod (shape-only); numeric/string
  bounds and `pattern` constraints are emitted into zod. Python owns strict timestamp/format checks.

## Root changes needed

- **`pnpm-lock.yaml` was updated** (new `packages/core-ir/ts` importer + catalog resolutions:
  zod, vitest, @vitest/coverage-v8, tsup, tsx, json-schema-to-typescript, @types/node, typescript 5.9).
  This is committed on this branch; the orchestrator owns the root lockfile, so flagging it here.
- No edits to `package.json`, `pnpm-workspace.yaml`, `turbo.json`, `biome.json`, or `tsconfig.base.json`
  were needed.
- Per PLAN §11, `packages/core-ir/ts` pins a package-local `typescript@^5.9.0` because `tsup`'s d.ts
  bundler requires the TypeScript compiler API, which TypeScript 7 no longer ships. The rest of the
  repo stays on TypeScript 7.
