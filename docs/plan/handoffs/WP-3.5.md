# WP-3.5 — `harness-tests` handoff

Status: **complete for the deterministic replay/conformance scope that exists on
`main` at `ff31d8a` (WP-3.2).** WP-3.3 (harness-agents) and WP-3.4
(harness-converge) were unmerged when this branch was cut, so specialist
conformance, router/scheduler invariants and a real-process RPC end-to-end test
are explicitly deferred (details below). Everything shipped here is green on the
current baseline with no root changes.

## What was built

All new code lives in owned paths: `packages/swarm-harness/ts/test/fixtures/**`,
`tests/swarm/**`, the swarm row of `docs/architecture/testing.md`, and this
handoff. No `src/**`, root file, lockfile, CI file, or frozen contract was
modified.

### Recording/replay fixtures (`packages/swarm-harness/ts/test/fixtures/`)

| File | Responsibility |
|---|---|
| `recordings.ts` | Versioned (`schema_version: 1`) `RecordedSession` zod schema; `validateRecording`/`parseRecording` (`RecordingValidationError`); `redactRecording`; canonical `serializeRecording`; directory loader; deterministic `ReplayProvider`/`createReplayProvider`; `isJsonPatchOp` guard. |
| `fixture-daemon.ts` | Fully deterministic in-memory `HarnessDaemon` (`FixtureDaemon`): rev tracking with real `ConflictError`, lock table with real `LockedError`, per-call gate batches, tool list/results, observable call history and `locksReleased`. |
| `report.ts` | `buildSessionReport` + `formatSessionReport`: outcome, state path, decisions, patch paths, tool calls, gate transitions, lock acquire/release and minor-unit spend. No timestamps, transcript paths or raw tool args; strings pass through `redactText`. |
| `support.ts` | Fixture loaders, temp project roots, `definitionFor`, gate/tool builders, `assertDefined`. |
| `sessions/*.json` | 5 committed recordings: `ee-erc-pass`, `fw-tool-verify`, `mech-conflict-retry`, `ee-gate-retry-pass`, `ops-budget-escalate`. |
| `README.md` | Fixture format, validation rules, replay semantics, how to add/update fixtures, nightly-live boundary. |

### Tests (31 new, 74 total in the package)

- `recordings.test.ts` — loads/validates every committed fixture; rejects stale
  schema versions, payload-less patch/tool decisions, unknown agents and
  malformed patch ops; redaction of sensitive keys/bearer tokens; canonical
  serialization; `ReplayProvider` order, deep-clone isolation, turn-mismatch
  failure, exhaustion and tolerant mode.
- `replay-e2e.test.ts` — drives the real WP-3.2 `runAgent` through the
  `HarnessDaemon` port with `FixtureDaemon` + `ReplayProvider`: patch→DAG→gates
  PASS, allow-listed tool call PASS, optimistic conflict re-read/retry PASS,
  gate FAIL→PASS retry, cost-cap ESCALATE, lock-contention ESCALATE with partial
  release, pre-run ABORT, and byte-identical report output across two runs.
- `budget-invariants.test.ts` — 48 seeded (mulberry32) cases; asserts bounded
  turns (`≤ maxTurns`), bounded cost overshoot (`≤ cap + max turn cost`), exact
  accounting against consumed usage, `consumed === turns`, lock release on every
  path, PASS only on all-PASS gates, and deterministic replay.
- `report.test.ts` — summary shape, token redaction, no timestamps/args/secrets,
  conflict counting, deterministic output and the empty-event case.

## How to verify (exact commands)

From the repository root:

```bash
pnpm install --frozen-lockfile
pnpm --filter @atomc/core-ir build
pnpm --filter @atomc/daemon-client build

pnpm --filter @atomc/swarm-harness test          # 11 files, 74 tests
pnpm --filter @atomc/swarm-harness test:coverage # thresholds: 85%
pnpm --filter @atomc/swarm-harness typecheck
pnpm --filter @atomc/swarm-harness lint
pnpm --filter @atomc/swarm-harness build
pnpm exec biome check packages/swarm-harness/ts
```

Observed: 74/74 tests pass; coverage 96.44% statements / 89.74% branches / 100%
functions / 96.19% lines; `tsc --noEmit`, `biome check` and tsup build clean.
Runtime is ~0.4 s with no network, Python, hardware or API keys.

## Design decisions

- **Fixtures are hand-authored and versioned, never recorded from a live model in
  PR CI.** No credentials exist and provider output is nondeterministic; a
  checked-in `schema_version` plus schema validation makes drift loud.
- **`ReplayProvider` asserts the request `turn`.** A recording that no longer
  matches the harness loop fails immediately instead of replaying silently.
- **The E2E targets the `HarnessDaemon` port.** That is exactly the seam the
  real `DaemonClientAdapter` implements over RPC, so the transactional loop is
  covered without a daemon process. Errors are the real `@atomc/daemon-client`
  `ConflictError`/`LockedError` classes.
- **The report is derived only from events + result**, so it is diffable and
  safe to attach to CI. It deliberately omits `startedAt`, `evaluated_at`,
  `transcriptPath` and tool arguments.
- **Property tests are seeded and bounded** (48 cases, ≤7 turns each) rather than
  timing/load based; the same seeds reproduce on Node 22 and 25.

## Deviations from contract

None. No frozen contract was changed. `docs/architecture/testing.md` was edited
only in the swarm-harness row, as the brief allows.

## Deferred (explicitly, per orchestrator direction for this pass)

1. **Specialist-definition conformance** — proving `ee/fw/mech/ops` definitions
   obey frozen ids, gate ownership, lock scopes, manifest `produces`/tools and
   budgets. Depends on WP-3.3's `AGENT_DEFINITIONS`/`AgentRegistry`, which exist
   only as uncommitted files in the WP-3.3 worktree. The generic machinery here
   (fixture daemon, replay provider, report) is ready to consume that registry.
2. **Router/scheduler invariants** — gate-failure routing, parallel scheduling
   under the lock graph, conflict rollback. Depends on WP-3.4, which has no code
   yet.
3. **Real-process daemon⇄client RPC E2E** — `runAgent` over the actual
   `DaemonClientAdapter` against `atomcd serve`. `tests/rpc` already covers the
   raw RPC surface; the harness-level variant belongs in `tests/swarm`, which
   needs the root workspace entry described below before it can run.
4. **Nightly live-model run with cost cap** — remains opt-in, separate from PR
   CI, and out of scope until credentials/approval exist.

## Open issues

- `tests/swarm/` currently contains only a README describing the deferred
  package; it is not in the pnpm workspace, so nothing there runs yet.
- When WP-3.3/3.4 land, add conformance + router invariants in a follow-up
  WP-3.5b (or extend this worktree after rebase) and rebase the recorded fixtures
  onto the final `AgentDefinition` shape.

## Root changes needed (orchestrator-owned)

1. **`pnpm-workspace.yaml`** — when the real-RPC E2E is implemented, add:
   ```yaml
   - "tests/swarm"
   ```
   (Same pending pattern as `tests/rpc`; do not add until that package exists.)
2. **`pnpm-lock.yaml`** — regenerate with the new importer when (1) lands.
3. **CI / Turbo** — add a swarm contract task only if a `tests/swarm` package is
   created. The already-required coverage job (`pnpm --filter
   @atomc/swarm-harness test:coverage`) now exercises the new tests with no extra
   services. No CI service, secret or runner dependency is required for this
   WP's committed scope.
