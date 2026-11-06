# WP-3.4 — `harness-converge` handoff

Status: **complete for deterministic convergence scheduling**. The package passes 98 fake-provider
tests (up from 96 in the core) with 92.92% statements, 86.15% branches, 98.92% functions and 94.44%
lines coverage on `converge.ts`-inclusive runs. The CLI passes 61 tests. No live provider, sockets,
API keys or hardware are used. Integration with WP-3.3's registry/provider adapter is deliberately
left as an explicit seam (see below).

## What was built

Two layers on top of `@atomc/swarm-harness`'s `runAgent`:

| Source                                            | Responsibility                                                                                                                 |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `packages/swarm-harness/ts/src/converge.ts`       | The convergence scheduler: gate snapshot → failure routing → parallel batches → fresh gate re-read → bounded retry/escalation. |
| `packages/swarm-harness/ts/test/converge.test.ts` | 22+ convergence tests over a scripted daemon/provider pair.                                                                    |
| `apps/atomc-cli/src/commands/converge.ts`         | `atomc converge` with an injected `ConvergenceRuntime`; honest `unavailable` without one.                                      |
| `apps/atomc-cli/src/deps.ts`                      | Secret-free `ConvergenceRunRequest`/`ConvergenceRunReport` types and the optional runtime slot on `CliDeps`.                   |
| `apps/atomc-cli/test/converge.test.ts`            | CLI-level tests: unavailable path, option validation, exit codes, JSON payload shape.                                          |

## Convergence loop

1. Read daemon gate results (`runGates`). An **empty snapshot is never converged**: it checkpoints
   as `unavailable` (no handler → escalate) with the reason "daemon returned no gate results".
   This prevents a plugin-less daemon from minting a false PASS.
2. Route each blocking `FAIL`/`ERROR` to its owner agent via the registry
   (`agentsForGate` override, else `GateResult.owner_agent`), falling back to per-agent `gates`
   lists. Unknown owners checkpoint as `unroutable`.
3. Group woken agents into batches with **disjoint lock scopes** and run each batch in parallel;
   overlapping scopes are serialized into later batches.
4. After the batch, re-read gate results from the daemon. Only the daemon's fresh state decides
   `converged` — the same no-false-PASS rule `runAgent` already enforces per session.
5. Track aggregate budgets: `maxCostMinor` (integer cents), `maxTokens`, and `maxTurns`
   (default 32) shared across all agents. Each batch receives a divided share of the remaining
   budget; a provider that overruns its share in a single call can still overspend (providers are
   not hard-billed), but the aggregate cap stops further scheduling and the overrun is surfaced in
   the result/reasons rather than hidden.
6. No-progress detection: a repeated gate-failure signature across rounds triggers a
   `no_progress` checkpoint. Round extensions via checkpoint `continue` are counted and capped.
7. Cancellation: an aborted `AbortSignal` returns `aborted` between rounds, mid-round after
   in-flight runs settle, and on error. The CLI wires SIGINT to this signal.

### Rollback

Failed runs are rolled back under the `escalate` policy (default): failed and retried agent scopes
are snapshot before the run and restored after `runAgent` releases its locks. Rollback retries
revision conflicts (bounded), records restored scopes as a `rollback` event, and failure to
rollback is escalated, never swallowed. `conflict` policy rolls back only on conflict outcomes;
`none` disables it.

### Honesty rules

- `converged` requires ≥1 gate result and zero blocking failures, read fresh from the daemon.
- `ERROR`, unroutable owners, exhausted budgets, aborts, provider crashes, round limits and empty
  snapshots all terminate with a non-`converged` status and a recorded reason.
- The audit log is bounded and low-detail (no prompts, no tool payloads).
- The CLI exits `0` only on `converged`, `1` on any incomplete/error outcome, `3` when no runtime
  is injected (never a fake PASS).

## Public API additions

`converge`, `ConvergeOptions`, `ConvergeResult`, `ConvergeStatus`, `ConvergeEvent`,
`ConvergenceRegistry` (structural: WP-3.3's `AgentRegistry` satisfies it), `ProviderFactory`,
`ConvergenceModelHost`, `CheckpointContext`, `CheckpointDecision`, `CheckpointReason`,
`RollbackPolicy`, `ConvergeAuditEntry`, `defaultIsConverged`, `scopesOverlap`, `splitBudget`.

## Integration with WP-3.3 (explicit, not merged here)

This branch intentionally does **not** depend on the WP-3.3 registry or pi-ai adapter:

- `converge({ registry, providerFor })` takes them as injected seams. WP-3.3's
  `AgentRegistry` satisfies `ConvergenceRegistry` structurally, and its provider factory fits
  `ProviderFactory`/`ConvergenceModelHost`.
- The CLI's `convergenceRuntime` is optional; the published binary reports `unavailable` (exit 3)
  until an integrating host wires one. `createConvergenceRuntime(run)` is the host seam.
- The orchestrator should wire the real registry/provider at integration time and add one
  deterministic end-to-end test through `converge` with WP-3.5's replay fixtures.

## Verification

From repository root (all green at handoff):

```bash
pnpm --filter @atomc/swarm-harness test        # 98 tests
pnpm --filter @atomc/swarm-harness test:coverage
pnpm --filter @atomc/swarm-harness typecheck build
pnpm --filter @atomc/cli test                  # 61 tests
pnpm --filter @atomc/cli typecheck build
pnpm exec biome check packages/swarm-harness apps/atomc-cli
pnpm exec turbo run build test typecheck
```

## Test inventory — convergence highlights

- Empty initial gate snapshot escalates (never converged).
- Gate snapshot becoming empty mid-run escalates honestly.
- Aggregate token cap and aggregate provider-turn cap across rounds.
- Parallel batches for disjoint scopes; serialization for overlapping scopes; max-locked-scope
  invariant asserted on the fake daemon.
- Multi-owner gate routing (`bom.cost_under_budget`-style) wakes both owners.
- Rollback on give-up/escalate/retry outcomes; rollback conflict retry; rollback failure
  escalation; lock cleanup awaited when a provider fails mid-batch.
- No-progress checkpoint on a repeated failure signature; capped round extensions.
- Cancellation between rounds and mid-round.
- Custom convergence predicate cannot be reached with zero gate results without a provider call.
- CLI: unavailable without a runtime, request forwarding, exit codes for all statuses, numeric
  option validation, human summary on stderr, `createConvergenceRuntime` seam.

## Known limitations / follow-ups

- Provider overrun within one call can exceed a share; caps are scheduling stops, not strict
  billing ceilings (documented in the README and the options).
- Snapshots for rollback are taken before agent locks and restored after release; a concurrent
  writer between those points can produce a revision conflict that rollback retries or escalates.
  A daemon-level transactional history would remove the window; deferred to Phase 4.
- Real-process RPC E2E and live provider runs remain deferred (WP-3.5 defers them too).
