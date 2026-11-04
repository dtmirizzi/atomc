# WP-1.2 `core-ir-ts` — TypeScript types + zod schemas for system_ir.json

Read `_common.md` first. Contract: `docs/architecture/contracts/ir-schema.md` §6.

## Owned paths
`packages/core-ir/ts/**`.

## Context
WP-1.1 (running in parallel) produces `packages/core-ir/schema/system_ir.schema.json` and fixtures
in `packages/core-ir/fixtures/`. Until it lands on `origin/wp/1.1-core-ir-py`, build your generator
against a small hand-written stand-in schema in `packages/core-ir/ts/test/stub.schema.json`. Poll
with `git fetch origin && git show origin/wp/1.1-core-ir-py:packages/core-ir/schema/system_ir.schema.json`
— once present, copy it in (don't merge their branch) to test, and finally read it from the real path.

## Deliverables
1. Package `@atomc/core-ir` (`packages/core-ir/ts/package.json`, ESM, exports `.` → `dist/index.js` + d.ts).
2. `scripts/gen.ts` (run with `tsx`, `pnpm --filter @atomc/core-ir gen`): reads the JSON Schema →
   (a) TS types via `json-schema-to-typescript` → `src/generated/types.ts`,
   (b) zod 4 schemas → `src/generated/zod.ts`. Write your own small JSON-Schema→zod emitter covering
   the subset Pydantic emits ($defs/$ref, objects w/ additionalProperties false, enums/Literal,
   anyOf for Optional, arrays, min/max, pattern, discriminated unions if any). Pick one approach,
   justify in handoff. Generated files ARE committed. `gen --check` fails on drift.
3. `src/index.ts`: `SystemIR` type, `SystemIRSchema`, `parseSystemIR()`, `SCHEMA_VERSION`,
   `JsonPatchOp` type, `patch(path).add/replace/remove/…build()` builder, typed `getAt(ir, pointer)`.
4. Vitest: every fixture in `packages/core-ir/fixtures/*.json` parses; every `fixtures/invalid/*.json`
   fails (or a documented subset — referential integrity is Python-only in v0.1, note it); drift
   test; builder tests. Coverage ≥ 85 %.
5. scripts: `build` (tsup), `test`, `typecheck` (`tsc --noEmit`), `gen`, `lint`.

## Definition of done
`pnpm install && pnpm --filter @atomc/core-ir gen && pnpm --filter @atomc/core-ir test && pnpm --filter @atomc/core-ir typecheck && pnpm --filter @atomc/core-ir build` all green against the REAL schema from WP-1.1. Handoff + push.
