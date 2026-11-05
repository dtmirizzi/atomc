# WP-3.2 — `harness-core` handoff

Status: **complete for the deterministic core**. The package passes 44 distinct fake-provider tests. Coverage: 95.14% statements, 88.46% branches, 100% functions, 94.8% lines. Tests use no live provider, sockets, API keys, or hardware. A real pi-ai/OpenRouter provider adapter is not included; see follow-up notes.

## What was built

`@atomc/swarm-harness` at `packages/swarm-harness/ts` (ESM, CJS, DTS via tsup) and `packages/swarm-harness/README.md`.

| Source | Responsibility |
|---|---|
| `src/types.ts` | Agent/session, gate failure, patch/tool/turn decisions, budget, events, `HarnessDaemon` and `ModelProvider` ports. |
| `src/state-machine.ts` | Frozen state/event transition table, history/subscriptions, terminal state helpers. Aborts from active states route through lock release. |
| `src/runner.ts` | `runAgent`: scoped IR read, lock acquisition, model decision loop, tool/patch checks, DAG and gate verification, budgets, conflict recovery, abort handling, transcript writes and cleanup. |
| `src/transcript.ts` | Redacted append-only JSONL, user redaction patterns, path-segment validation and size rotation. |
| `src/daemon-adapter.ts` | Thin adapter from the daemon client to the harness daemon port. |

### Public API

Runtime exports include `runAgent`, `SwarmStateMachine`, `StateTransitionError`, `transition`, `isTerminal`, `TranscriptWriter`, `DaemonClientAdapter`, `redactEntry`, `redactText`, `redactValue`, `SENSITIVE_KEYS`, `DEFAULT_REDACT_PATTERNS`, `isWithinScopes`, `isToolPermitted`, `AGENT_NAMES`, `AGENT_STATES`, `AGENT_EVENTS`, `TRANSITIONS`, and `TERMINAL_STATES`.

Types include `AgentBudget`, `AgentDefinition`, `AgentName`, `AgentPatchProposal`, `AgentRunResult`, `AgentSession`, `AgentState`, `AgentToolCall`, `AgentTurn`, `AgentEvent`, `GateFailure`, `HarnessDaemon`, `ModelConfig`, `ModelDecision`, `ModelProvider`, `ModelRequest`, `RunOutcome`, `RunAgentOptions`, `SwarmEvent`, `ToolDescriptor`, `TranscriptOptions`, and `TurnUsage`.

### State flow

```text
IDLE → PLAN → CLAIM_LOCK → ACT → VERIFY → RELEASE → DONE | RETRY | ESCALATE | ABORTED
                           ↑         │
                           └ RETRY_TURN
```

All terminal outcomes are reached after best-effort lock release. A stale revision triggers re-read and a fresh model turn, never a blind patch resend. The model cannot claim success; actual daemon gate results decide `PASS`. Tool calls must be allow-listed, discovered from the daemon, and validate against the advertised JSON Schema. Patches must fit both lock scopes and any declared `produces` scopes.

## Verification

From repository root:

```bash
pnpm --filter @atomc/swarm-harness verify
pnpm --filter @atomc/swarm-harness test:coverage
pnpm exec biome check packages/swarm-harness/ts
```

The brief's literal `pnpm --filter @atomc/swarm-harness test typecheck lint build` passes extra argv to Vitest; use the package `verify` script or separate invocations.

## Test inventory — 44 distinct tests, 7 files

Fixtures are in `test/fakes.ts`; no test file imports another test module.

- `state-machine.test.ts` (5): frozen transition history; retry/escalation routes; abort through RELEASE; invalid edge behavior; subscriptions/unsubscribe.
- `transcript.test.ts` (6): sensitive-key/token redaction; custom redaction patterns; circular values; traversal-safe IDs; JSONL write/path; rotation.
- `runner-pass.test.ts` (2): gate-driven PASS and all-lock release; model give-up escalates.
- `tools.test.ts` (4): disallowed tool; schema-invalid args; permitted-but-undiscovered tool; valid permitted invocation.
- `runner-failure.test.ts` (3): bounded RETRY then ESCALATE; crashed gate; exhausted cost budget.
- `runner-edges.test.ts` (17): scope boundaries; tool grant matching; malformed patch/tool decisions; tool failure; server conflict recovery; over/exact cost cap; over/exact token cap; invalid usage; budget before next turn; manifest `produces` boundary; throwing observer; advisory/skip gates; targeted DAG/gate routing; missing optional tool discovery.
- `runner-locks.test.ts` (7): complete lock lifetime; unlock failure cleanup; provider throw; pre-lock abort; lock contention; stale revision replanning; current revision and write-scope enforcement.

## Design decisions and limitations

- `HarnessDaemon` and `ModelProvider` remain narrow injectable ports. CI uses in-memory daemon and scripted model fakes.
- `PASS` is derived from daemon gates only; advisory failures and skipped gates do not block, `ERROR` escalates.
- Costs/tokens are normalized to non-negative finite integer counts and checked before another action or verification.
- Provider adapter wiring, streaming accounting and recorded provider replays remain future work; no pi-ai dependencies are needed by the deterministic core.
- `produces` is enforced in addition to `lockScopes`. Confirm contract semantics with WP-3.3/WP-3.4 before relying on wider/narrower interpretations.
- There is no daemon end-to-end test in this package; Studio/daemon integration and convergence suites own that boundary.

## Root integration

This WP did not edit root files. The orchestrator integrated the workspace importer and lockfile with the Phase 3 CLI/Studio workspaces. `pnpm install --frozen-lockfile`, root Turbo build/test/typecheck and CI are part of integration verification.
