# WP-2.1 `plugin-sdk-ts` — handoff

## What was built

`@atomc/plugin-sdk` at `packages/plugin-sdk/ts/` plus the committed cross-language schema
artifact at `packages/plugin-sdk/schema/atomc-plugin.schema.json` (contract v0.1.0).

- **`src/manifest.ts`** — strict Zod 4 manifest schema (`AtomcPluginManifestSchema`) matching
  `docs/architecture/contracts/plugin-manifest.md`, with defaults (`watches[].files` → `[]`,
  `watches[].debounce_ms` → `250`), `additionalProperties: false` everywhere, per-manifest
  cross-field refinements, and `validatePluginManifest(data, context)` /
  `parsePluginManifest(data, context)` for cross-manifest checks.
- **`src/schema.ts`** + **`scripts/generate-schema.ts`** — deterministic `z.toJSONSchema(...)`
  emission (`--check` fails on drift) of `packages/plugin-sdk/schema/atomc-plugin.schema.json`.
- **`src/plugin.ts`** — `defineAtomcPlugin({ manifest, setup }, context?)` returning a frozen
  `AtomcPlugin` descriptor (`gates` by gate id, `tools` by tool name, `cli` by command), typed
  `PluginContext` / `PluginSetupContext` host interfaces, `GateResultSchema`, registration errors.
  No side effects at import; host services are unavailable during `setup()`.
- **`src/watches.ts`** — `watchMatches` / `watchMatchesIr` / `watchMatchesFiles` over IR pointers
  and file globs. Debounce remains daemon-owned metadata.
- **`src/conformance.ts`** — `conformance` / `assertConformance`, `validateToolInput` (via
  `z.fromJSONSchema`), `assertAgentAccess`, `isWithinProduces`, `findTool`,
  `PluginConformanceError`.
- **`src/pointer.ts`** / **`src/glob.ts`** / **`src/semver.ts`** — RFC 6901 helpers (+ exported
  pattern strings), dependency-free POSIX glob matcher, SemVer/range syntax validators. All
  patterns are exported into the JSON Schema artifacts.
- **Tests** — 97 Vitest tests across manifest, pointer, glob, watches, plugin, conformance and
  schema-parity (`contract.test.ts`). Coverage 95% lines / 88% functions (threshold 85%).
- **`packages/plugin-sdk/README.md`** — third-party quick start; its manifest example validates.

### Exact `src/index.ts` exports

Values: `APPROVED_TOP_LEVEL_SCOPES`, `AtomcCliSchema`, `AtomcGateSchema`,
`AtomcPluginManifestSchema`, `AtomcRuntimeSchema`, `AtomcToolSchema`, `AtomcUiSchema`,
`AtomcWatchSchema`, `BUILTIN_CLI_COMMANDS`, `GATE_SEVERITIES`, `MANIFEST_NAME_PATTERN`,
`MANIFEST_VERSION`, `OWNER_AGENTS`, `PluginManifestError`, `parsePluginManifest`,
`validatePluginManifest`, `GateResultSchema`, `PluginRegistrationError`, `defineAtomcPlugin`,
`normalizeWatchPath`, `watchMatches`, `watchMatchesFiles`, `watchMatchesIr`, `assertAgentAccess`,
`assertConformance`, `conformance`, `findTool`, `isWithinProduces`, `PluginConformanceError`,
`validateToolInput`, `escapePointerToken`, `isPointerDescendant`, `isValidPointer`, `joinPointer`,
`JsonPointerError`, `parsePointer`, `pointerMatchesPattern`, `pointersEqual`,
`unescapePointerToken`, `isSafeRelativePath`, `matchesAnyGlob`, `matchesGlob`,
`normalizeProjectPath`, `isSemver`, `isSemverRange`, `generateManifestJsonSchema`,
`MANIFEST_SCHEMA_ID`, `parsePluginManifest`.

Types: `ApprovedTopLevelScope`, `AtomcCli`, `AtomcGate`, `AtomcPluginManifest`, `AtomcRuntime`,
`AtomcTool`, `AtomcUi`, `AtomcWatch`, `GateSeverity`, `ManifestIssue`, `ManifestValidationContext`,
`ManifestValidationResult`, `OwnerAgent`, `AtomcPlugin`, `AtomcPluginOptions`, `CliHandler`,
`GateEvidence`, `GateHandler`, `GateResult`, `GateSuggestion`, `IrTransactionOp`,
`IrTransactionResult`, `PluginArtifacts`, `PluginCache`, `PluginContext`, `PluginEvents`,
`PluginIr`, `PluginLogger`, `PluginSetup`, `PluginSetupContext`, `ToolHandler`, `ChangeSet`,
`ConformanceIssue`, `ConformanceReport`.

## How to verify

```bash
pnpm install --frozen-lockfile                     # after orchestrator adds the lock importer
pnpm --filter @atomc/plugin-sdk schema:generate
pnpm --filter @atomc/plugin-sdk schema:check
pnpm --filter @atomc/plugin-sdk test               # 97 tests
pnpm --filter @atomc/plugin-sdk test:coverage      # >=85% thresholds
pnpm --filter @atomc/plugin-sdk typecheck
pnpm --filter @atomc/plugin-sdk lint
pnpm --filter @atomc/plugin-sdk build              # ESM + CJS + .d.ts
pnpm exec biome check packages/plugin-sdk/ts       # clean coverage/dist first
```

Local verification used `pnpm install --no-frozen-lockfile` (the root lockfile lacks the
`packages/plugin-sdk/ts` importer) and reverted `pnpm-lock.yaml` before committing.

## Cross-language packaging advice (for WP-2.2 and CI)

- The Python SDK should validate against `packages/plugin-sdk/schema/atomc-plugin.schema.json`
  (Draft 2020-12), not a hand-written shape. The schema encodes: all types/enums/patterns,
  `additionalProperties: false`, `manifest_version` const, `watches.files`/`debounce_ms` defaults,
  the runtime `anyOf` requirement, and approved `produces` scope pattern.
- JSON Schema **cannot** express array-item uniqueness (watch/gate/tool/cli/ui ids) or `after`
  reference integrity. These are semantic checks mirrored by each SDK's validator; keep the rule
  set in this file as the source of truth and add equivalent Python tests.
- `atomc-plugin.schema.json` is generated; never edit by hand. Regeneration is deterministic and
  guarded by `schema:check` and `contract.test.ts`.

## Design decisions

- **Patterns over refinements.** Wherever possible, contract rules are expressed as `.regex(...)`
  (`version`, `atomc`, pointer, produces scope, handler, relative path) so they land in the JSON
  Schema and are enforced cross-language. Refinements remain for cross-field/semantic rules.
- **Runtime requirement as a union** of two strict objects → JSON Schema `anyOf`, so Python
  enforces "at least one runtime" without custom code.
- **Self-contained SDK.** Pointer/glob/semver helpers are duplicated here; `@atomc/plugin-sdk`
  does not depend on `@atomc/core-ir` or the daemon.
- **Symmetric-subtree pointer matching.** A watch matches when either pointer is an
  ancestor-or-equal of the other; `*` matches exactly one segment; globs are anchored at the
  project root.
- **Immutable descriptors** via deep-freeze + a read-only map wrapper.
- **Handler registration keyed by declared handler name**, then projected to gate id / tool name /
  command; a single implementation name may be shared by multiple declarations of the same kind.
- Package-local `typescript@^5.9` (tsup DTS needs the TS compiler API that TS 7 dropped) and
  `vite: "catalog:"` (mirrors WP-1.2 to avoid the VitePress vite-5 resolution clash).

## Deviations from contract

None in the data shape. Two contract ambiguities were resolved conservatively and must be ruled on:

1. **CLI built-in shadowing is self-contradictory.** The contract says plugin `cli[].command`
   values "cannot shadow built-in `atomc` commands", but the contract's own example declares
   `command: "quote"` — a built-in per PLAN §3 (WP-3.1). Enforcing the reserved list by default
   would invalidate the frozen example, so the SDK exports `BUILTIN_CLI_COMMANDS` as data and only
   rejects shadowing when the host passes `reservedCliCommands` to `validatePluginManifest`.
   **Requested ruling:** confirm the built-in command list and whether plugins may reuse those
   names (e.g. via `atomc <plugin> <command>` namespacing).
2. **Fields without documented defaults are required.** Only `watches[].files` (→ `[]`) and
   `watches[].debounce_ms` (→ `250`) are specified as having defaults, so `gates[].after`,
   `tools[].agents`, `tools[].mutates` are required (empty arrays/false still allowed). If the
   intent was defaulting these too, say so and I will update schema + defaults.

## Open issues

- `reservedCliCommands` is opt-in pending the ruling above; the built-in list mirrors PLAN §3
  WP-3.1 and will drift if that CLI surface changes.
- Cross-field rules are enforced by the Zod validator but only structurally by the JSON Schema;
  Python must implement the same semantic checks (documented above).
- `contract.test.ts` explicitly classifies three fixtures (`bad-after`, `duplicate-watch-id`,
  `mutating-tool-no-produces`) as semantic-only; expand if JSON Schema can cover them later.

## Root changes needed

- **Add the `packages/plugin-sdk/ts` importer to `pnpm-lock.yaml`** (deps: `zod`; dev:
  `@types/node`, `@vitest/coverage-v8`, `tsup`, `tsx`, `typescript@^5.9.0`, `vite`, `vitest`).
  Orchestrator owns the lockfile; run `pnpm install` on merge. I did **not** commit any
  `pnpm-lock.yaml` change.
- No edits to `package.json`, `pnpm-workspace.yaml`, `turbo.json`, `biome.json`, or
  `tsconfig.base.json` were needed.
