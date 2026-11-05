# WP-2.1 `plugin-sdk-ts` — TypeScript plugin SDK

Read `_common.md`, `PLAN.md` §§2, 4, 9, `docs/architecture/contracts/plugin-manifest.md`, and `gate-result.md` fully. The v0.1 contracts are frozen. Python SDK, daemon and client agents are starting in parallel; honor the exact manifest/RPC types in those contracts and do not change them.

## Owned paths
- `packages/plugin-sdk/ts/**`
- `packages/plugin-sdk/schema/**` (generated JSON Schema, committed)
- `packages/plugin-sdk/README.md`

Do not modify `pnpm-lock.yaml`, root workspace files, Python SDK paths, daemon paths, or the contract docs. If a workspace importer is needed, request the root lockfile update in `HANDOFF.md`; orchestrator owns lockfiles.

## Deliverables
1. `packages/plugin-sdk/ts/package.json`, name `@atomc/plugin-sdk`, private during v0, Apache-2.0, ESM, `exports` for runtime and type declarations; scripts `build`, `test`, `typecheck`, `lint`, `schema:generate`, `schema:check`, `contract`. Use catalog dependencies (`zod`, `typescript`, `tsup`, `vitest`, `@types/node`). Use Zod 4 APIs; avoid a separate JSON-Schema dependency unless required.
2. `src/manifest.ts`: strict Zod schema exactly matching plugin-manifest.md, including defaults, cross-field refinements and clear path-specific validation errors. Export `AtomcPluginManifestSchema`, inferred `AtomcPluginManifest`, `parsePluginManifest`, `validatePluginManifest`, and `MANIFEST_VERSION`.
3. Cross-field invariants from the contract: kebab-case name; SemVer version; `atomc` range; at least one runtime; unique watch ids, gate ids, tool names; valid JSON pointers; only approved top-level `produces` scopes and never `/meta`; `after` references declared watch ids (or provide a validation context for cross-manifest references); gate owner/severity enums; agents subset; mutating tools require declared write scopes; unique CLI command and UI panel ids; UI entry cannot escape package root; no unknown keys.
4. `src/plugin.ts`: `defineAtomcPlugin({manifest, setup})` returning an immutable descriptor. Define typed `PluginContext` (IR get/transact, artifact root, logger, cache, abort signal, events) without binding to a daemon implementation. Setup registers gate/tool/CLI handlers. Reject undeclared, duplicate, missing handlers and non-matching handler names. No side effects at module import.
5. `src/watches.ts`: deterministic matcher for changed JSON pointers and project file paths. JSON pointer matching: exact, parent/child subtree, escaped `~0/~1`; `*` wildcard per segment only if explicitly supported/documented. File globs use a current maintained glob library only if necessary; keep semantics documented and test normalized POSIX relative paths. Debounce is daemon-owned metadata, not SDK timers.
6. `src/conformance.ts`: manifest and implementation conformance API reusable by built-in plugins and third parties. Validate tool input JSON against declared JSON Schema (use Zod's JSON Schema representation or a small validator dependency only if necessary); assert requested agent access; ensure mutation permissions fit `produces`; ensure all declared handlers are implemented.
7. `scripts/generate-schema.ts`: deterministic `z.toJSONSchema(AtomcPluginManifestSchema)` generation to `packages/plugin-sdk/schema/atomc-plugin.schema.json`; `--check` fails on drift. Include schema metadata `$id`, title, `manifest_version` constraint. JSON Schema is the single cross-language data contract; Python SDK consumes this artifact rather than maintaining a different shape.
8. Vitest suites: valid/invalid manifest fixtures, every cross-field rule, handler conformance, JSON pointer escaping and watch matching, JSON Schema parity (generated schema validates the same fixtures), deterministic generation. Use a fake minimal plugin.
9. `README.md`: third-party quick start and manifest fields; examples must validate against schema.

## Definition of done
From root (after orchestrator adds lock importer if needed): `pnpm install --frozen-lockfile`, `pnpm --filter @atomc/plugin-sdk schema:generate`, `schema:check`, `test`, `typecheck`, `lint`, `build`, and `pnpm exec biome check packages/plugin-sdk/ts` all pass. Write `HANDOFF.md` at `docs/plan/handoffs/WP-2.1.md`, commit and push `wp/2.1-plugin-sdk-ts`. In handoff list exact exports and any cross-language packaging advice for the schema.
