# WP-3.10 — `swarm-e2e-rpc` handoff

Status: **complete and green locally.** The new `tests/swarm` package spawns the
real `atomcd serve` process over WebSocket RPC and drives `converge()` through
`DaemonClientAdapter`. Three E2E paths pass (converge-to-PASS, optimistic
conflict retry, abort-by-signal lock cleanup). The daemon process is asserted
dead after every test. No root workspace, lockfile, CI, package, app or
`tests/rpc` file was modified in the committed tree.

## What was built

All new code lives in owned paths.

| Path | Responsibility |
| --- | --- |
| `tests/swarm/package.json` | `@atomc/swarm-e2e` wiring mirroring `tests/rpc`: `build:deps` builds `@atomc/daemon-client`, `@atomc/core-ir` and `@atomc/swarm-harness`; `test`/`typecheck`/`lint` scripts. |
| `tests/swarm/tsconfig.json`, `tests/swarm/vitest.config.ts` | Extends `tsconfig.base.json`; Vitest is serial (`fileParallelism: false`) with 300 s test/hook timeouts because each file spawns Python. |
| `tests/swarm/ts/harness.ts` | Real-daemon harness copied from the WP-2.6 `tests/rpc` pattern (not imported across suites): throwaway project/state dirs, canonical core-ir minimal fixture, fake plugin, `uv run --project <repo> --all-packages atomcd serve`, `/health` + `daemon.json` wait, token-redacted bounded logs, `connect()`/`connectAdapter()`, `finally`-safe `stop()`, and `assertProcessDead()`. |
| `tests/swarm/ts/fixtures/fake-plugin.ts` | Deterministic Python fake plugin (copied/adapted from `tests/rpc/ts/fixtures/fake-plugin.ts`): one watch `swarm-fake:refresh`, one **blocking** gate `gate:swarm-e2e.ready` owned by `ee-agent`, one read tool. The gate PASSes only when `/electrical/nets` is non-empty. |
| `tests/swarm/ts/fixtures/ir.ts` | Minimal `/electrical` node (empty nets) and the `net:N0` the scripted provider appends. |
| `tests/swarm/ts/converge.e2e.test.ts` | The three `converge()` E2E specs over real RPC. |
| `tests/swarm/README.md` | Describes the layer, the three paths, determinism rules and how to run it locally. |
| `docs/architecture/testing.md` | Only the swarm-harness row was updated to include the real-daemon E2E and the `tests/swarm` location. |

### E2E paths proved

1. **Converge to PASS** — a scripted `ModelProvider` reads the live `base_rev`
   from the model request and patches `/electrical/nets` through the real
   `ir.transact`; the daemon evaluates `gate:swarm-e2e.ready` on real IR and
   returns `PASS`. Asserts: `result.status === "converged"`, the fresh
   `gateResults[0].status === "PASS"`, `ir_rev` advanced, a follow-up
   `ir.lock("/electrical", …)` succeeds and unlocks, and the JSONL transcript
   contains no bearer/token material (a deliberately planted
   `Bearer sk-…` rationale is redacted to `[REDACTED]`).
2. **Optimistic-conflict retry** — the first provider turn deliberately returns
   `baseRev: 0` against a rev-1 node; the runner detects the stale revision,
   re-reads, replans, and the second turn patches with the correct `baseReV`.
   Asserts convergence, `provider.calls >= 3`, advanced revision, released locks
   and a `patch.conflict` transcript entry.
3. **Abort-by-signal with lock cleanup** — the provider aborts an injected
   `AbortController` mid-session; `runAgent` observes the abort, releases every
   acquired subtree lock in its `finally`, and `converge()` returns
   `aborted`. Asserts a follow-up `ir.lock` succeeds and unlocks.

## How to verify (exact commands)

The package is not yet in `pnpm-workspace.yaml`, so `pnpm --filter` cannot resolve
its `@atomc/*` dependencies on a clean checkout. Build the deps directly and run
Vitest from the package:

```bash
pnpm install --frozen-lockfile
pnpm --filter @atomc/daemon-client build
pnpm --filter @atomc/core-ir build
pnpm --filter @atomc/swarm-harness build
cd tests/swarm && ./node_modules/.bin/vitest run --reporter=verbose
```

Observed locally (macOS arm64, Node 25.1.0, pnpm 10.30.3, `uv` 0.9.8):

```text
✓ ts/converge.e2e.test.ts > swarm convergence over real daemon + RPC > converges to PASS ... 733ms
✓ ts/converge.e2e.test.ts > swarm convergence over real daemon + RPC > recovers from an optimistic conflict ... 633ms
✓ ts/converge.e2e.test.ts > swarm convergence over real daemon + RPC > aborts on signal and releases locks 615ms
Test Files  1 passed (1)
     Tests  3 passed (3)
  Duration  2.28s
```

Once the workspace entry lands, the normal commands are:

```bash
pnpm --filter @atomc/swarm-e2e test       # pretest builds deps first; 3 passed
pnpm --filter @atomc/swarm-e2e typecheck  # tsc --noEmit, clean
pnpm --filter @atomc/swarm-e2e lint       # biome check ts vitest.config.ts, clean
```

The suite was run three times in a row with no state leakage (fresh daemon and
temp tree per test; `assertProcessDead()` after teardown).

## Design decisions

- **Copy the harness, don't import it.** Per the brief, `tests/swarm/ts/harness.ts`
  and the fake plugin are self-contained copies of the WP-2.6 pattern so the two
  test suites cannot break each other.
- **Reuse the real gate path.** The fake gate reads `/electrical` through the
  plugin host's `ir_read`, so the result is genuinely derived from daemon IR
  state, not from a test-only shortcut.
- **Coordinator is the source of truth.** `converge()` re-reads gates from the
  daemon with the prefixed `gate:` id after each round; the agent's own
  `runGates` ids are normalized (no prefix) by the existing WP-3.4
  `definitionForRun`, so the final convergence decision always comes from a
  fresh real gate snapshot even if the per-agent verification uses a normalized
  id.
- **`rollback: "none"` in the E2E options.** The brief does not require rollback
  and the default `escalate` policy would attempt a post-release rollback
  transact with a holder that no longer owns the lock. Disabling rollback keeps
  the E2E focused on the three required paths.
- **Determinism.** Ephemeral loopback port (bind 0), per-test temp project and
  state dirs, no vendor keys, no network beyond loopback, serial Vitest file
  execution, bounded token-redacted daemon logs, and `finally`-safe teardown.

## Deviations from contract

None. No frozen contract (`agent-protocol.md`, `rpc.md`, `gate-result.md`,
`ir-schema.md`, `plugin-manifest.md`) was changed. The RPC calls the tests make
(`ir.get`, `ir.transact`, `ir.lock`, `ir.unlock`, `dag.run`, `gates.run`,
`daemon.shutdown`) all match the v0.1 contract.

## Open issues

- `tests/swarm` is not yet in the pnpm workspace or Turbo/CI graph; it cannot
  be discovered by `pnpm --filter @atomc/swarm-e2e` on a clean checkout until
  the root change below lands.
- The gate id used inside an agent's own verification is without the `gate:`
  prefix (existing WP-3.4 normalization). The coordinator's final snapshot uses
  the prefixed id, so convergence is honest; if a future daemon build requires
  the prefix at `gates.run`, the agent path would need the same normalization
  applied consistently. No change is needed in this WP.
- The tests cover the three required paths only; specialist-definition
  conformance and router/scheduler invariants remain in the package's
  deterministic suite (WP-3.5 surface), which was intentionally not modified.

## Root changes needed (orchestrator-owned)

1. **`pnpm-workspace.yaml`** — add the swarm package (and, when convenient, the
   still-pending `tests/rpc` entry):

   ```yaml
   packages:
     - "apps/*"
     - "packages/*/ts"
     - "plugins/*/ts"
     - "docs"
     - "tests/contract"
     - "tests/rpc"
     - "tests/swarm"
   ```

2. **`pnpm-lock.yaml`** — regenerate with the new importers
   (`pnpm install --no-frozen-lockfile`); the swarm importer adds only
   `@atomc/daemon-client`, `@atomc/swarm-harness` and the cataloged
   `@types/node`, `@types/ws`, `typescript`, `vite`, `vitest`, `ws`.
3. **CI / Turbo** — add a **separate** CI job (not folded into the TS unit-test
   job) because the suite spawns Python via `uv`. Suggested job:

   ```yaml
   swarm-e2e:
     runs-on: ubuntu-latest
     steps:
       - uses: actions/checkout@v4
       - uses: pnpm/action-setup@v4
       - uses: actions/setup-node@v4
         with: { node-version: 22 }
       - run: corepack enable && pnpm install --frozen-lockfile
       - run: curl -LsSf https://astral.sh/uv/install.sh | sh
       - run: pnpm --filter @atomc/swarm-e2e test
   ```

   Estimated runtime on a warm uv cache: **~10–15 s** wall clock (the three
   daemons start in under a second each); budget **5–10 min** for the first run
   because `uv run` syncs Python 3.14 and all workspace Python packages. Turbo
   can expose it as `contract`/`test` for the `@atomc/swarm-e2e` package once it
   is in the workspace; `pnpm install` and `uv sync` must run before the filter
   command.
