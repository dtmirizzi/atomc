# WP-3.4 `harness-converge` — gate routing and bounded convergence

Read `_common.md`, PLAN §§0, 1, 4, 5, 6, 8, 9; `docs/architecture/contracts/{agent-protocol,gate-result,rpc}.md`; the merged harness/client/daemon packages and WP-3.3 handoff. The daemon owns IR and gate truth. `runAgent` owns one transactional specialist run. This work coordinates runs; never duplicate either boundary.

## Owned paths
- `packages/swarm-harness/ts/src/converge/**`
- `packages/swarm-harness/ts/test/converge/**`
- `packages/swarm-harness/ts/README.md`
- `apps/atomc-cli/src/commands/converge.ts`
- `apps/atomc-cli/test/converge.test.ts`
- `docs/plan/handoffs/WP-3.4.md`

Coordinate overlap with WP-3.3 before editing shared harness/CLI files. Do not edit root files, lockfiles, CI, daemon, client or frozen contracts.

## Deliverables
1. Deterministic gate router: route blocking failures to `owner_agent`, reject/hold unknown owners and `ERROR` gates for coordinator review, ignore advisory failures for scheduling, and keep a bounded audit trail.
2. Convergence scheduler: read current gate state, schedule only eligible agent definitions, respect overlapping lock-scope conflicts, allow safe independent specialists to run in parallel only if cancellation/cleanup can be awaited, then re-fetch actual daemon gates. `PASS` requires zero blocking FAIL and zero ERROR results; never accept an agent self-report.
3. Termination controls: maximum rounds, turn/cost/token budget accounting (integer minor currency), abort signal, no-progress/repeated-failure detection, daemon/provider failure handling, and human checkpoint/escalation events. Do not turn skipped/unavailable checks into PASS.
4. Retry policy is explicit, bounded, and tested: retries only after fresh gate/IR reads. Conflicts and partial failures must not start duplicate runs or lose lock cleanup. Every completion waits for all spawned `runAgent` calls to release locks.
5. `atomc converge` integration: options for project, max rounds, max cost and JSON output; machine-readable single JSON document; honest nonzero exit for incomplete/aborted/escalated runs; no fake success if plugins/agents/provider are missing. TTY output summarizes blockers, owner decisions, spend and final daemon gate state.
6. Tests with FakeDaemon/FakeProvider and deterministic gates for: routing by owner, unknown/error/advisory gates, overlapping vs disjoint scopes, parallel completion and cleanup, budget ceilings, abort, no-progress detection, gate changes between rounds, all-pass convergence, and JSON/exit status. No network/hardware/model keys.
7. README and handoff document configuration, limits, orchestration boundaries and exact tests.

## Definition of done
- CLI and harness unit tests, coverage, typecheck, lint, build all pass.
- Coverage floors remain satisfied; no broad coverage exclusions.
- `pnpm exec turbo run build test typecheck` passes after orchestrator integrates lockfiles.
- Playwright/CI checks remain green on Node 22 and 25, Python 3.14 Linux/macOS.
- Commit/push to `wp/3.4-harness-converge`; do not merge.

## Stop and ask

Coordinate with WP-3.3 about provider/registry APIs and resolve concurrency semantics with the orchestrator before coding if the contract does not settle them. Do not add a dependency or root lock edit unilaterally. No live vendor keys are available.
