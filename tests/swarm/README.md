# `tests/swarm` — cross-package swarm convergence tests (WP-3.5)

Reserved for swarm **cross-package** tests that need the real daemon process over
RPC plus the harness loop:

- daemon ⇄ `@atomc/daemon-client` ⇄ `DaemonClientAdapter` ⇄ `runAgent`
  with a recorded/fake provider,
- failure → routed agent → checked patch/tool → DAG/gates → final gate state,
- optimistic conflict, lock cleanup and abort against the real server.

## Status: deferred

The deterministic half of WP-3.5 is implemented inside
`packages/swarm-harness/ts/test/fixtures/**` and runs under the package's Vitest
(`pnpm --filter @atomc/swarm-harness test`): versioned recording fixtures, a
deterministic `ReplayProvider`, a fixture `HarnessDaemon`, budget invariants and
the session report utility. Those tests do not touch the network, a Python
process, credentials, or unmerged WP-3.3/WP-3.4 code.

This directory is intentionally not a package yet. A real-process RPC E2E needs:

1. **`pnpm-workspace.yaml`** — add `- "tests/swarm"` (mirrors the pending
   `- "tests/rpc"` entry; both are orchestrator-owned root changes).
2. **`pnpm-lock.yaml`** — regenerate with the new importer.
3. **CI** — a job that provisions `uv`/Python 3.14 (like `tests/rpc`) and runs
   `pnpm --filter @atomc/swarm-tests test`, plus a Turbo `contract`/`test` task.

Once WP-3.3 and WP-3.4 land, this package should also host specialist-definition
conformance and router/scheduler invariant tests. See
`docs/plan/handoffs/WP-3.5.md` for the exact request.
