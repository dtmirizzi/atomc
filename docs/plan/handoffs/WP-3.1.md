# WP-3.1 `cli` — handoff

Branch: `wp/3.1-cli` · Status: **done, green** · Depends on: `@atomc/daemon-client`,
`@atomc/core-ir`, `@atomc/plugin-sdk`, frozen contracts `docs/architecture/contracts/{rpc,plugin-manifest,ir-schema}.md`.

## What was built

New pnpm workspace package **`@atomc/cli`** at `apps/atomc-cli` (Commander 15, ESM + CJS +
`.d.ts` via tsup, `bin.atomc → dist/index.js`).

**Command tree** (`atomc <command>`):

- `init <dir>` — copies `examples/atomc-pad` (or `--template <name>`) into the target, rewrites
  the project `name`/`project_id` in `system_ir.json` (re-validated with `parseSystemIR`) and the
  `project:` field in `atomc.config.ts`. Skips `build/`, `node_modules/`, `.venv/`, `.git/`,
  `.ato/`, `dist/`, `coverage/`, `__pycache__/`, QMK build artifacts. Refuses a non-empty target
  unless `--force`. Handles paths containing spaces.
- `build [target]` — `ensureDaemon` → optional `events.subscribe` → `dag.run` (passes
  `targets`/`force`) → polls `dag.status` to settle (bounded by `--timeout`, default 120 s) →
  `gates.list` → prints run id, node states, gate counts and blocking failures. Exit `1` on a
  failed node or blocking `FAIL`; never reports success for an empty DAG.
- `doctor` — combines CLI version, daemon discovery/health/`/schema`, version agreement, and
  local tool probes (`uv` required; `ato`, `qmk`, `renode`, `build123d` optional). Statuses
  `PASS|WARN|SKIP|FAIL`; exit non-zero only on `FAIL`.
- `daemon start|status|stop` — via `@atomc/daemon-client` (`ensureDaemon` / pid-file discovery /
  `daemon.shutdown`). `status`/`stop` never spawn a daemon.
- `plugin list` — `plugins.list` rendered as a table or `--json`.
- `plugin new <name>` — generates `atomc-plugin.json`, entrypoint(s) and a test scaffold for
  `--runtime ts|python|both`; the manifest is validated with `@atomc/plugin-sdk`
  `validatePluginManifest` before any file is written; refuses non-empty dirs without `--force`.
- `sim`, `jig`, `quote`, `orders`, `converge` — **explicit stubs**: they attach to the daemon,
  check whether the required plugin is loaded, and emit a structured
  `{status:"unavailable"|"not_implemented", reason, hint}` result. They exit `3` and **never**
  report `PASS`. `converge` is left for `@atomc/swarm-harness` (WP-3.4).

**Testability**: every handler takes an injected `CliDeps` (`src/deps.ts`) covering IO, fs, clock,
sleep, repo-root lookup, `ensureDaemon`, `findDaemon`, `probeDaemon`, `probeTools`. Tests use an
in-memory `FakeFs` and a scripted `FakeDaemon`, so no daemon, network, or hardware is touched.
`src/default-deps.ts` is the only real-IO module and is excluded from coverage by design.

## Public API

`src/program.ts` exports `buildProgram(deps): Command` and `runCli(deps, argv?): Promise<number>`
(never throws; returns the process exit code). `src/default-deps.ts` exports
`createDefaultDeps(overrides?)`. Exit codes: `0` success, `1` error/FAIL, `3` planned
capability unavailable.

## Tests (52 Vitest tests, 7 files)

`doctor` (version agreement/mismatch, not-running warning, required-tool failure, schema header,
health false, thrown probe), `daemon` (start/status/stop json + human), `init` (copy+rewrite,
ignore rules, force guard, spaces, missing template, missing config), `build` (clean, targets,
failed node, blocking gate, empty DAG, invalid timeout, subscribe failure, failure events,
timeout, human output), `plugin` (manifest validates, python/both runtimes, invalid name,
overwrite guard, list), `capability` (all five never PASS, missing vs installed plugin, human),
`program` (help, version, unknown command, `--json` single-document discipline, version lock-step
with `scripts/release/VERSION`, unexpected handler error).

Coverage (v8): **95.55% stmts / 85.99% branches / 87.5% funcs / 98.23% lines** (threshold 85%).

## How to verify (exact commands, from repo root)

```bash
# The root lockfile must first gain the apps/atomc-cli importer (see below), then:
pnpm install --frozen-lockfile
pnpm --filter @atomc/core-ir build
pnpm --filter @atomc/plugin-sdk build
pnpm --filter @atomc/daemon-client build
pnpm --filter @atomc/cli build
pnpm --filter @atomc/cli test
pnpm --filter @atomc/cli test:coverage   # deletes coverage/ afterwards
pnpm --filter @atomc/cli typecheck
pnpm --filter @atomc/cli lint
pnpm exec biome check apps/atomc-cli    # run after deleting apps/atomc-cli/coverage
pnpm exec turbo run build test typecheck lint
node apps/atomc-cli/dist/index.js --help
```

Verified green locally on macOS arm64, Node 25, pnpm 10.30.3. Note: `test:coverage` writes
`apps/atomc-cli/coverage/` (gitignored); delete it before the direct biome check because biome
would otherwise format the generated `coverage-summary.json`.

## Design decisions

- **No second RPC client / daemon.** `daemon` and `plugin list` use `@atomc/daemon-client`
  directly; `doctor` discovers the daemon through the `~/.atomc/daemon.json` pid file and HTTP
  `/health` + `/schema` without spawning.
- **Dependency injection everywhere.** The command tree is pure over `CliDeps`, so the full CLI
  is unit-tested without daemons or hardware, satisfying the brief's "fakes only" requirement.
- **`--json` stdout discipline.** Every command defines its own `--json` and emits exactly one
  JSON object to stdout; all human text/diagnostics go to stderr. (A shared parent `--json`
  option was removed because Commander 15 let the parent shadow the subcommand value.)
- **Planned commands are honest.** `sim`/`jig`/`quote`/`orders`/`converge` return exit `3` with a
  structured reason. A missing plugin reports `unavailable`; a present-but-unwired feature
  reports `not_implemented`. No fake `PASS` anywhere.
- **Templates are copied from `examples/`** via a `findRepoRoot()` walk (repo checkout), with
  `init` rewriting project identity. `plugin new` writes a minimal valid manifest (watch + one
  advisory placeholder gate) that passes the frozen `@atomc/plugin-sdk` schema.
- **No top-level `await`** in the entrypoint (kept CJS-buildable); `runCli(...).then(set
  process.exitCode)`.

## Deviations from contract

None. RPC usage matches `rpc.md` (`dag.run`/`dag.status`/`gates.list`/`plugins.list`/
`daemon.shutdown`/`events.subscribe`); generated manifests match `plugin-manifest.md`; init
re-validates IR against `ir-schema.md` via `@atomc/core-ir`.

## Open issues

- `findRepoRoot()` walks up from `process.cwd()` for the `examples/` templates. Running `atomc
  init` from outside a repo checkout has no template to copy; bundling templates into the
  published package is deferred (noted in README).
- `atomc.config.ts` is honored only for project-root/name conventions in this WP; typed config
  loading (via `tsx`/`jiti`) is not yet wired into individual commands. `tsx` is declared as a
  devDependency for local `pnpm dev`.
- `converge` is intentionally unimplemented until `@atomc/swarm-harness` (WP-3.4) lands.
- `plugin new` Python entrypoints are syntactic scaffolds; only the JSON manifest is validated in
  this WP.

## Root changes needed

- **`pnpm-lock.yaml`** — add exactly one importer for `apps/atomc-cli`:

  ```yaml
  apps/atomc-cli:
    dependencies:
      '@atomc/core-ir': { specifier: workspace:*, version: link:../../packages/core-ir/ts }
      '@atomc/daemon-client': { specifier: workspace:*, version: link:../../packages/daemon-client/ts }
      '@atomc/plugin-sdk': { specifier: workspace:*, version: link:../../packages/plugin-sdk/ts }
      commander: { specifier: 'catalog:', version: 15.0.0 }
    devDependencies:
      '@types/node': { specifier: 'catalog:', version: 25.9.9 }
      '@vitest/coverage-v8': { specifier: 'catalog:', version: 5.1.0(vitest@5.1.0) }
      tsup: { specifier: 'catalog:', version: 9.0.0(postcss@8.5.32)(tsx@4.23.15)(typescript@5.9.3)(yaml@2.9.1) }
      tsx: { specifier: 'catalog:', version: 4.23.15 }
      typescript: { specifier: ^5.9.0, version: 5.9.3 }
      vitest: { specifier: 'catalog:', version: 5.1.0(@types/node@25.9.9)(@vitest/coverage-v8@5.1.0)(vite@8.3.5(@types/node@25.9.9)(esbuild@0.28.2)(tsx@4.23.15)(yaml@2.9.1)) }
  ```

  No new package resolutions and no catalog changes are required — every non-workspace dependency
  (`commander`, `tsx`, `vitest`, `tsup`, `@types/node`, `@vitest/coverage-v8`, `typescript`) is
  already resolved in the existing lockfile.
- No other root file changes.
