# `tests/swarm` — real-daemon swarm convergence E2E (WP-3.10)

This package proves the swarm harness boundary against a **real** `atomcd`
process over the WebSocket JSON-RPC transport. Unlike the deterministic
fixture-daemon tests that live inside `packages/swarm-harness` (WP-3.5), every
test here spawns `atomcd serve` with `uv run`, connects the real
`@atomc/daemon-client`, wraps it in `DaemonClientAdapter`, and drives
`converge()` end to end.

## Layout

| Path | Responsibility |
| --- | --- |
| `ts/harness.ts` | Throwaway project + state dir, canonical IR fixture, fake plugin, real `atomcd serve` spawn, `/health` wait, token-redacted logs, `finally`-safe teardown. Copied from the WP-2.6 `tests/rpc` pattern, not imported across suites. |
| `ts/fixtures/fake-plugin.ts` | Deterministic fake Python plugin (one watch, one blocking gate `gate:swarm-e2e.ready`, one read tool). The gate passes only when `/electrical/nets` is non-empty. |
| `ts/fixtures/ir.ts` | Minimal `/electrical` node and the net the scripted provider appends. |
| `ts/converge.e2e.test.ts` | Three `converge()` E2E paths over real RPC. |

## What the spec covers

Each test starts its own daemon, creates `/electrical` with an empty `nets`
list, and asserts the daemon process is dead after teardown.

1. **Converge to PASS** — a scripted provider patches `/electrical/nets` over
   real RPC; the fake plugin's blocking gate flips from `FAIL` to `PASS`; the
   final `converge()` gate snapshot (read fresh from the daemon) is `PASS`, the
   IR revision advanced, a follow-up `ir.lock` succeeds, and the transcript
   contains no bearer/token material.
2. **Optimistic-conflict retry** — the first provider turn answers with a stale
   `base_rev`; the runner rebases on the daemon's fresh revision, retries, and
   converges. The transcript records `patch.conflict`.
3. **Abort-by-signal lock cleanup** — the provider aborts an `AbortController`
   mid-session; the run terminates `aborted` and the agent's subtree lock is
   released (a follow-up `ir.lock` succeeds).

Determinism: no fixed ports (the harness binds an ephemeral loopback port), no
vendor keys, no network beyond loopback, and generous startup/per-test timeouts
(180 s / 300 s) for the first `uv` sync.

## How to run it locally

The package must be present in the pnpm workspace before `pnpm --filter` can
resolve its `@atomc/*` dependencies. Until the orchestrator adds the workspace
entry (see the WP-3.10 handoff), build the deps directly and run Vitest:

```bash
# 1. build the workspace deps the harness imports
pnpm --filter @atomc/daemon-client build
pnpm --filter @atomc/core-ir build
pnpm --filter @atomc/swarm-harness build

# 2. run the E2E (from tests/swarm, using its linked node_modules)
cd tests/swarm && ./node_modules/.bin/vitest run --reporter=verbose
```

Once `pnpm-workspace.yaml` includes `- "tests/swarm"` (and the lockfile is
regenerated), the normal commands work:

```bash
pnpm --filter @atomc/swarm-e2e test
pnpm --filter @atomc/swarm-e2e typecheck
pnpm --filter @atomc/swarm-e2e lint
```

CI needs a separate job rather than folding into the TS unit-test job, because
each run spawns Python via `uv`. Suggested job commands and runtime are in the
handoff.
