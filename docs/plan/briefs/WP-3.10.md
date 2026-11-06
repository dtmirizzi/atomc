# WP-3.10 `swarm-e2e-rpc` — convergence over a real daemon process and real RPC

Read `_common.md`, PLAN §§4, 6, 8, 9; the frozen `docs/architecture/contracts/{agent-protocol,rpc,gate-result}.md`; the WP-3.2/3.3/3.4/3.5 handoffs; and `tests/rpc/ts/harness.ts` (the proven real-daemon harness pattern from WP-2.6). The swarm harness `converge()` currently runs E2E only against the in-memory `FixtureDaemon`. This package proves the real boundary: Python daemon + WebSocket RPC + `DaemonClientAdapter`.

## Owned paths
- `tests/swarm/**` (harness, specs, fixtures)
- `tests/swarm/package.json` (mirror the tests/rpc package wiring)
- `docs/architecture/testing.md` (only the swarm test row)
- `docs/plan/handoffs/WP-3.10.md`

Do not edit root workspace/lockfile/CI, packages, apps or tests/rpc. Request CI wiring in the handoff (exact commands) — the orchestrator owns the root Turbo/CI change.

## Deliverables
1. A `tests/swarm/ts/harness.ts` that reuses the WP-2.6 pattern: throwaway project dir, canonical IR from the core-ir fixture, the deterministic fake gate plugin (see `tests/rpc/ts/fixtures/fake-plugin.ts` — copy, do not import across test suites), spawn real `atomcd serve` via `uv run`, wait for health, and return a real `DaemonClient` plus cleanup that is `finally`-safe.
2. `DaemonClientAdapter` end-to-end: load IR, transact a scoped patch (real optimistic-concurrency on the daemon side), lock/unlock subtrees, run DAG, read gates — all through the adapter from `@atomc/swarm-harness`.
3. One `converge()` E2E spec: a scripted provider whose patch fixes the fake plugin's failing gate; assert the run converges with real daemon gate results, the IR revision advanced, locks are released (a follow-up lock attempt succeeds), and the transcript/report contain no secrets. Cover at least: converge-to-PASS, optimistic-conflict retry path, abort-by-signal with lock cleanup.
4. Determinism: no fixed ports (bind port 0 / ephemeral), generous startup timeouts, teardown that never leaks processes (verify in a dedicated test or teardown assert), no network beyond loopback, no vendor keys. Tests must pass on Node 22 and 25 and on Linux CI runners.
5. A README under `tests/swarm/` describing the layer and how to run it locally.
6. Handoff: exact commands, coverage of paths, deviations, and the CI/Turbo request (job commands + estimated runtime; suggest a separate CI job, not folding into test-ts, since it spawns Python).

## Definition of done
- `pnpm --filter @atomc/swarm-e2e test` (or your package name) passes locally twice in a row (no state leakage between runs).
- The daemon process is verified dead after every test (teardown assertion).
- Biome + typecheck clean for your paths; no changes outside owned paths.
- Conventional commits; push `wp/3.10-swarm-e2e-rpc`; do not merge.

## Stop and ask
If the fake plugin cannot produce a gate that fails-then-passes deterministically over real RPC, or the adapter's port mismatch blocks a needed call, stop and report the exact RPC gap instead of mocking around it.
