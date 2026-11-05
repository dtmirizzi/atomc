# WP-2.6 `rpc-contract-tests` — handoff

Branch `wp/2.6-rpc-contract-tests` · private package `@atomc/rpc-contract-tests` (`tests/rpc`) ·
depends on merged WP-2.3 (`atomc-daemon`) and WP-2.5 (`@atomc/daemon-client`).

## What was built

A new private pnpm package that drives the **real `atomcd` process** with the **real
`@atomc/daemon-client`** over `ws://127.0.0.1:<port>/rpc` — not a mock server. 34 Vitest tests
across 9 files, all green on macOS arm64 (Node 25, pnpm 10.30.3, Python 3.14/uv).

- `tests/rpc/package.json` — `@atomc/rpc-contract-tests`, scripts `build:deps`, `contract`,
  `test`, `typecheck`, `lint` (plus `pre*` hooks that build `@atomc/daemon-client`/`@atomc/core-ir`).
- `tests/rpc/ts/harness.ts` — `DaemonHarness.start(options)`:
  - creates a fresh temp root (`mkdtemp` + `realpath`), writes the canonical minimal
    `packages/core-ir/fixtures/minimal.json` as `system_ir.json`, the embedded fake Python plugin
    as `fake_rpc_plugin.py`, and a frozen-contract-valid `plugins/rpc-fake/atomc-plugin.json`;
  - allocates a free loopback port (port 0 probe, then closes), spawns
    `uv run --project <repo> --all-packages atomcd serve …` with argv and **no shell**, with the
    project root prepended to `PYTHONPATH` and `ATOMCD_*` env stripped;
  - waits for `daemon.json` + `/health` (bounded), reads the bearer token from the file, never
    prints it, and redacts it from all captured output;
  - exposes `connect()` (real `DaemonClient`), `httpJson()`, `readState()`, `pidFileExists()`,
    `waitForProcessExit()`, and `stop()`; teardown tries `daemon.shutdown`, then `SIGTERM`, then
    `SIGKILL`, then removes the temp tree, in `afterAll` even on assertion failure;
  - `expectPolicyClose()` (raw `ws` upgrade → close code 1008) and `waitForEvent()` (polling with
    bounded timeout, never a bare sleep).
- `tests/rpc/ts/fixtures/fake-plugin.ts` — deterministic Python plugin + manifest: one watch
  (`rpc-fake:refresh`, watches `/keyboard`), two gates (`gate:rpc-fake.ok` = deterministic PASS,
  `gate:rpc-fake.fail` = advisory FAIL), one read tool (`read_status`), one mutating tool
  (`add_net`) scoped to its declared `/electrical` `produces`.
- `tests/rpc/ts/fixtures/ir.ts` — canonical `/electrical`, `/keyboard` and dangling-ref snippets.
- Tests:
  - `health.test.ts` — `/health` shape; `/schema` deep-equals the committed core-ir JSON Schema.
  - `auth.test.ts` — missing/wrong token close 1008; valid token connects and serves.
  - `ir.test.ts` — root/subtree revs, valid patch rev bump + changed paths, stale `-32010`,
    validation `-32012`, dangling ref `-32013`, rollback leaves data/revs unchanged.
  - `locks.test.ts` — lock, cross-holder `-32011`, holder mutation, wrong-holder unlock, release.
  - `plugins.test.ts` — `plugins.list`, `tools.list` agent filtering, read tool result, mutating
    write + rev bump, out-of-`produces` write → `-32020` with no state change.
  - `gates.test.ts` — `gates.run`/`gates.list`, `PASS` persisted at `/gates/results/rpc-fake.ok`,
    advisory `FAIL` isolation, run-all.
  - `dag.test.ts` — `dag.status`, targeted `dag.run`, `dag.node.start/end`, `gate.result`,
    reactive invalidation on a watched pointer without an explicit `dag.run`.
  - `events.test.ts` — `ir.changed` and `gate.result` delivery, `events.unsubscribe` stops delivery.
  - `daemon.test.ts` — `daemon.status`, `daemon.shutdown`, process exit + pid-file removal, stale
    dead-pid `daemon.json` cleanup on start.
- `tests/rpc/README.md` — required environment, commands, coverage summary.

## How to verify (exact commands)

After the orchestrator adds `tests/rpc` to `pnpm-workspace.yaml` and regenerates `pnpm-lock.yaml`
(see below):

```bash
pnpm install --frozen-lockfile
pnpm --filter @atomc/rpc-contract-tests contract
pnpm --filter @atomc/rpc-contract-tests typecheck
pnpm --filter @atomc/rpc-contract-tests lint
pnpm exec turbo run contract
```

Locally verified in this worktree with the workspace wired on top of merged `main`:

```
pnpm --filter @atomc/rpc-contract-tests contract   → 9 files / 34 tests passed (~32 s)
pnpm --filter @atomc/rpc-contract-tests typecheck  → tsc --noEmit clean
pnpm --filter @atomc/rpc-contract-tests lint       → biome clean (16 files)
pnpm exec turbo run contract                       → 5 tasks successful (tests/contract + tests/rpc)
```

A fresh-environment smoke (`UV_PROJECT_ENVIRONMENT=/tmp/uvfresh … vitest run ts/health.test.ts`)
confirms the harness's `uv run --all-packages` self-bootstraps the Python workspace in a clean
checkout (~11 s once download/cache warm), so the CI `contract` job does not need a prior
`uv sync` (though adding one is harmless and recommended).

No Python files were added or edited; ruff/mypy are unaffected.

## Design decisions

- **Real daemon, real client, one daemon per file.** Each test file owns a private project/state
  tree and a private port. `vitest.config.ts` sets `fileParallelism: false` so the shared uv
  environment and the free-port probe are never raced.
- **Spawn command is `uv run --project <repo> --all-packages atomcd serve …`, not the brief's
  `uv run --project <repo> atomcd serve`.** The root uv project is `package = false`, so a clean
  checkout has no `atomcd` console script until workspace members are installed; the brief's exact
  argv fails with `Failed to spawn: atomcd`. `--all-packages` is the minimal fix and was verified
  against a throwaway `UV_PROJECT_ENVIRONMENT`. This is the only command deviation.
- **Watch pointer is `/keyboard`, not `/electrical`.** Any successful `ir.transact` calls
  `DagScheduler.notify_ir_changed`, which (debounce 0) immediately runs the watch and its
  descendant gates and writes `/provenance` + `/gates` — each write bumps the document revision.
  With the watch on `/electrical`, ordinary IR/tool tests raced those background runs and made
  revision assertions non-deterministic. Watching `/keyboard` keeps the fake DAG real (and now
  explicitly exercised in `dag.test.ts` by transacting `/keyboard` and awaiting
  `dag.node.start` for `rpc-fake:refresh`) while `/electrical` mutations used by the IR/locks/tools
  tests stay outside the watch coverage. The mutating tool still writes only `/electrical`.
- **Stale-pid fixture uses pid 0.** `pid_alive(0) == False`, so the daemon deterministically clears
  the pre-written state without depending on any real pid being dead.
- **`uv run` is spawned with argv** (`stdio: ["ignore","pipe","pipe"]`), bounded toggling log
  buffer, and `ATOMCD_TOKEN/HOST/PORT/STATE_DIR` removed from the child env so the CLI/random token
  path (not the env override) is what the tests exercise.
- **`pre*` build hooks.** `pnpm --filter @atomc/rpc-contract-tests contract|test|typecheck`
  builds `@atomc/daemon-client` and `@atomc/core-ir` first, because their package `exports`
  resolve to `dist/` and the brief's DoD runs the filter directly (turbo's `^build` only covers
  `pnpm exec turbo run contract`).

## Deviations from contract

None. All methods, params/results, error codes, event topics, manifest rules and `GateResult`
fields asserted are exactly those in `docs/architecture/contracts/{rpc,ir-schema,plugin-manifest,
gate-result}.md`. The single non-contract deviation is the harness spawn argv documented above.

## Open issues

- **The package is not yet a workspace member in this branch.** The committed tree contains only
  `tests/rpc/**`; the root workspace/lock/CI wiring is orchestrator-owned (below). Until it lands,
  the DoD commands cannot run from a clean `main` checkout of this branch.
- **`/schema` is compared against the committed `packages/core-ir/schema/system_ir.schema.json`,**
  i.e. the schema `@atomc/core-ir` is generated from (the endpoint serves
  `export_json_schema()`). If a future core-ir change regenerates the schema, both sides move
  together; no drift.
- **Automatic file-glob watching is not exercised** (`watchfiles`); this suite covers IR-pointer
  reactivity only, matching the frozen contract's event surface.
- CI currently runs the Python side of the daemon tests on Linux/macOS; this suite self-skips
  nothing and is expected to run in the `contract` job (Linux) — it has no OS-specific branches.

## Root changes needed (orchestrator-owned)

1. **`pnpm-workspace.yaml`** — add one entry to `packages:`:

   ```yaml
   - "tests/rpc"
   ```

2. **`pnpm-lock.yaml`** — regenerate (`uv`/pnpm manager owns the lockfile). The only required
   importer addition is exactly:

   ```yaml
   tests/rpc:
     dependencies:
       '@atomc/daemon-client':
         specifier: workspace:*
         version: link:../../packages/daemon-client/ts
     devDependencies:
       '@types/node':
         specifier: 'catalog:'
         version: 25.9.9
       '@types/ws':
         specifier: 'catalog:'
         version: 8.18.2
       typescript:
         specifier: 'catalog:'
         version: 7.0.2
       vite:
         specifier: 'catalog:'
         version: 8.3.5(@types/node@25.9.9)(esbuild@0.28.2)(tsx@4.23.15)(yaml@2.9.1)
       vitest:
         specifier: 'catalog:'
         version: 5.1.0(@types/node@25.9.9)(@vitest/coverage-v8@5.1.0)(vite@8.3.5(@types/node@25.9.9)(esbuild@0.28.2)(tsx@4.23.15)(yaml@2.9.1))
       ws:
         specifier: 'catalog:'
         version: 8.22.1
   ```

   No new package resolutions, no catalog changes.

3. **`.github/workflows/ci.yml`** — wire the new package into the existing hash-gated steps:
   - `lint` job: add `'tests/rpc/package.json'` to the `hashFiles(...)` guard and `'tests/rpc/**'`
     to the `git ls-files` glob list for the biome step.
   - `typecheck` job: add `'tests/rpc/package.json'` to the `turbo run typecheck` `if:` guard.
   - `test-ts` job: add `'tests/rpc/package.json'` to the `turbo run build test` `if:` guard (the
     suite runs in `contract` instead, but the guard should not silently omit it).
   - `contract` job: add `'tests/rpc/package.json'` to the `Cross-language contract task` `if:`
     guard. Recommended: run `uv sync --all-packages` before `pnpm exec turbo run contract` so the
     job never depends on the harness's self-sync (it works either way — verified — but an explicit
     sync is cheaper and more predictable).
   - No `turbo.json` change: `contract`, `test`, `typecheck`, `lint` are auto-discovered; the
     existing `contract`/`test` `dependsOn: ["^build"]` builds `@atomc/daemon-client`/core-ir.
