# WP-3.2 — `harness-core` handoff

Status: **complete for the deterministic core**. 36 fake-provider tests pass, coverage is above the
brief's 85% floor (statements 94.8%, branches 87.02%, functions 100%, lines 94.71%). No live provider
calls, sockets, or API keys are used by tests. A real pi-ai/OpenRouter adapter is **not** included in
this WP; it is scoped as a follow-up below.

## What was built

Package `@atomc/swarm-harness` at `packages/swarm-harness/ts` (ESM + CJS + DTS via tsup), plus
`packages/swarm-harness/README.md`.

Source files:

| File | Responsibility |
|---|---|
| `src/types.ts` | Frozen protocol types: `AgentDefinition`, `AgentSession`, `GateFailure`, `AgentPatchProposal`, `AgentToolCall`, `AgentTurn`, `ModelConfig`, `AgentBudget`, `RunOutcome`, `SwarmEvent`, plus the `HarnessDaemon` and `ModelProvider` ports. |
| `src/state-machine.ts` | Explicit transition table and `SwarmStateMachine` with history/subscriptions. Invalid edges throw `StateTransitionError`; `trySend` ignores them. |
| `src/runner.ts` | `runAgent`: read scoped IR → lock → act (patch/tool) → targeted DAG + owned gates → release. Bounded retries, conflict re-read/replan, budget/token/turn caps, abort signal, transcript writes. |
| `src/transcript.ts` | `TranscriptWriter`: append-only JSONL at `.atomc/sessions/<run>/<agent>.jsonl`, 8 MiB rotation, recursive key redaction and bearer/API-key string scrubbing. |
| `src/daemon-adapter.ts` | `DaemonClientAdapter` binding `@atomc/daemon-client` to `HarnessDaemon`. Excluded from coverage because it is a thin transport shim. |
| `src/index.ts` | Public barrel. |

### Public API (all exports from `src/index.ts`)

Runtime values:

```ts
runAgent(options: RunAgentOptions): Promise<AgentRunResult>
class SwarmStateMachine            // send/trySend/onTransition/history/state
class StateTransitionError
transition(state, event)           // pure reducer
class TranscriptWriter             // append(entry), path
class DaemonClientAdapter          // implements HarnessDaemon
redactEntry / redactText / redactValue
SENSITIVE_KEYS / DEFAULT_REDACT_PATTERNS
isWithinScopes(path, scopes)
isToolPermitted(allowList, call)
AGENT_NAMES / AGENT_STATES
AGENT_EVENTS / TRANSITIONS / TERMINAL_STATES
isTerminal(state)
```

Exported types: `AgentBudget`, `AgentDefinition`, `AgentName`, `AgentPatchProposal`, `AgentRunResult`,
`AgentSession`, `AgentState`, `AgentToolCall`, `AgentTurn`, `AgentEvent`, `GateFailure`, `HarnessDaemon`,
`ModelConfig`, `ModelDecision`, `ModelProvider`, `ModelRequest`, `RunOutcome`, `RunAgentOptions`,
`SwarmEvent`, `ToolDescriptor`, `TranscriptOptions`, `TurnUsage`.

`RunAgentOptions` takes an injected `ModelProvider` (only `nextTurn(request): Promise<ModelDecision>`),
a `HarnessDaemon`, a `GateFailure`, an optional `AbortSignal`, and optional budget/conflict/verify
limits. `ModelDecision` is one of `patch`, `tool`, `verify`, or `give_up`.

### State diagram

```
IDLE --START--> PLAN --PLANNED--> CLAIM_LOCK --LOCKED--> ACT
  ACT --VERIFY_REQUESTED--> VERIFY --VERIFIED--> RELEASE
  VERIFY --RETRY_TURN--> ACT
  ACT --GIVE_UP/ACTION_FAILED--> RELEASE
  PLAN/CLAIM_LOCK/VERIFY --ACTION_FAILED--> RELEASE
  RELEASE --RELEASE_PASS--> DONE
  RELEASE --RELEASE_RETRY--> RETRY
  RELEASE --RELEASE_ESCALATE--> ESCALATE
  any active state --ABORT--> ABORTED
```

Locks are released in a `finally` block on every exit path, including pass, retry, give-up, provider
throw, abort, and lock conflict. An optimistic revision conflict re-reads the IR and asks the model
again; the stale patch is never resent. A blocking gate failure retries in-run at most
`maxVerifyRetries`, then yields `RETRY` while budget remains or `ESCALATE` when turns/budget run out.
`ERROR` gates escalate immediately. Agents cannot self-report success: only `runGates` results drive
`PASS`.

## How to verify (exact commands)

From the repo root:

```bash
pnpm --filter @atomc/swarm-harness verify
# equivalent to:
pnpm --filter @atomc/swarm-harness test
pnpm --filter @atomc/swarm-harness typecheck
pnpm --filter @atomc/swarm-harness lint
pnpm --filter @atomc/swarm-harness build
pnpm --filter @atomc/swarm-harness test:coverage

# Biome exactly as requested in the brief:
pnpm exec biome check packages/swarm-harness/ts
# or, from packages/swarm-harness/ts:
pnpm exec biome check --write src test tsup.config.ts vitest.config.ts
```

The literal brief command `pnpm --filter @atomc/swarm-harness test typecheck lint build` forwards
`typecheck lint build` as argv to the first script (vitest) and fails; use the separate invocations
above or the added `verify` script.

Root integration checks (run after the lock importer below is integrated):

```bash
pnpm install            # or pnpm install --frozen-lockfile once the lock is committed
pnpm build
pnpm test
```

## Tests — exact 36 executions across 7 files

Vitest reports 36 executions. Four files import shared fixtures from `runner-pass.test.ts`, so its two
base scenarios also execute inside those files (8 duplicate executions); unique scenarios are 28.
Duplicates are tracked as a test-organization follow-up below.

`test/state-machine.test.ts` (4)

1. walks the frozen loop and records history
2. routes retries back to ACT and escalation through RELEASE
3. throws on an invalid transition and trySend ignores it
4. notifies subscribers and can unsubscribe

`test/transcript.test.ts` (4)

5. redacts sensitive keys and token-shaped strings
6. handles circular references without throwing
7. writes redacted JSONL under `.atomc/sessions/<run>/<agent>.jsonl`
8. rotates when the file exceeds maxBytes

`test/runner-pass.test.ts` (2)

9. returns PASS and releases every lock when gates pass
10. does not trust a model that skips verification (give_up escalates)

`test/tools.test.ts` (4 = 2 own + 2 imported)

11. returns PASS and releases every lock when gates pass (imported)
12. does not trust a model that skips verification (give_up escalates) (imported)
13. rejects a tool outside the allow-list without calling the daemon
14. invokes a permitted tool with the holder id

`test/runner-failure.test.ts` (5 = 3 own + 2 imported)

15. returns PASS and releases every lock when gates pass (imported)
16. does not trust a model that skips verification (give_up escalates) (imported)
17. yields RETRY while budget remains, then escalates when turns run out
18. escalates on a crashed gate (ERROR) without domain retries
19. escalates after the cost budget is exhausted

`test/runner-edges.test.ts` (10 = 8 own + 2 imported)

20. returns PASS and releases every lock when gates pass (imported)
21. does not trust a model that skips verification (give_up escalates) (imported)
22. accepts a scope, its descendants, and never /meta
23. supports exact, plugin-wide, and global tool grants
24. escalates on a patch decision without a proposal
25. escalates on a tool decision without a call
26. escalates when a permitted tool throws
27. recovers from a server-side optimistic conflict
28. escalates when the token budget is exhausted
29. works with a daemon that exposes no tools

`test/runner-locks.test.ts` (7 = 5 own + 2 imported)

30. returns PASS and releases every lock when gates pass (imported)
31. does not trust a model that skips verification (give_up escalates) (imported)
32. releases locks when the provider throws
33. does not acquire locks when aborted before planning
34. escalates after bounded lock conflicts without leaking locks
35. re-reads and replans on a stale-rev proposal instead of blindly resending
36. applies a patch at the current revision and rejects writes outside its scopes

## Design decisions

- **Ports instead of transports.** `HarnessDaemon` and `ModelProvider` are narrow interfaces. The
  daemon adapter is separate and excluded from coverage; tests use in-memory fakes. This keeps the
  core deterministic and provider-free.
- **Gate-driven convergence.** `PASS` requires zero blocking `FAIL` gates and zero `ERROR` gates.
  Advisory `FAIL`s do not block. A model `give_up` always escalates.
- **Conflict policy.** A mismatch between the proposal's `baseRev` and the scoped read, or a server
  `ConflictError`, triggers `readScopes()` + another model turn. Bounded by
  `maxConflictRetries` (default 1); no blind resend.
- **Lock policy.** Every declared lock scope is acquired with the session holder id; release is
  reverse-order and best-effort in `finally` so one failed unlock does not strand the rest.
- **Transcripts are redacted before serialization.** Key names in `SENSITIVE_KEYS` become
  `[REDACTED]`; bearer tokens, `sk-*`, and GitHub-token-shaped strings are scrubbed. Rotation renames
  the active file to `.1`, `.2`, ….
- **TypeScript 5.9 locally.** Catalog `typescript` is `^7.0.2`, but every existing TS package in this
  repo uses `^5.9.0` for tsup DTS compatibility; this package follows the established local pattern.

## Deviations from contract / gaps

- **No real pi-ai adapter.** `@mariozechner/pi-ai` and `@mariozechner/pi-agent-core` are not added as
  dependencies and no adapter is implemented. The `ModelProvider` interface is the integration point.
  Wiring pi-ai/OpenRouter (including streaming usage/cost accounting) is a follow-up.
- **Tool argument schema validation.** Allow-listing is enforced, but `input_schema` from
  `tools.list` is not yet validated against `args`; malformed args reach the daemon. A zod validator
  in the adapter is the planned follow-up (zod is already a declared dependency).
- **`produces` scopes.** `AgentDefinition.produces` is carried but not enforced separately from
  `lockScopes`; writes are gated by lock scopes only. Needs contract clarification from WP-3.3/WP-3.4
  on whether `produces` is additive or an intersection with lock scopes.
- **DoD command syntax.** See "How to verify"; the literal multi-script `pnpm --filter` command does
  not work as written. Added `verify` as the working equivalent.
- **No daemon integration test here.** This WP is intentionally fake-only; WP-3.4/3.5 own end-to-end
  daemon convergence tests.

## Open issues

- Move shared `definition`/`failure` fixtures out of `runner-pass.test.ts`; four files import that
test module, so two scenarios execute five times and inflate the reported count from 28 unique to 36.
- Decide whether `produces` must be intersected with `lockScopes` (contract ambiguity).
- Add zod validation for tool args against `input_schema`.
- Implement and contract-test the real pi-ai/OpenRouter adapter outside the deterministic core.
- Transcripts currently rotate by byte size only; retention/pruning policy is not defined in the
  contract yet.

## Root changes needed (orchestrator-owned)

No root files were edited. The workspace glob `packages/*/ts` already picks up the package. The only
required integration is regenerating `pnpm-lock.yaml` so the new importer is recorded. Exact stanza
`pnpm install` produced locally:

```yaml
  packages/swarm-harness/ts:
    dependencies:
      '@atomc/core-ir':
        specifier: workspace:*
        version: link:../../core-ir/ts
      '@atomc/daemon-client':
        specifier: workspace:*
        version: link:../../daemon-client/ts
      zod:
        specifier: 'catalog:'
        version: 4.6.7
    devDependencies:
      '@types/node':
        specifier: 'catalog:'
        version: 25.9.9
      '@vitest/coverage-v8':
        specifier: 'catalog:'
        version: 5.1.0(vitest@5.1.0)
      tsup:
        specifier: 'catalog:'
        version: 9.0.0(postcss@8.5.32)(tsx@4.23.15)(typescript@5.9.3)(yaml@2.9.1)
      typescript:
        specifier: ^5.9.0
        version: 5.9.3
      vitest:
        specifier: 'catalog:'
        version: 5.1.0(@types/node@25.9.9)(@vitest/coverage-v8@5.1.0)(vite@8.3.5(@types/node@25.9.9)(esbuild@0.28.2)(tsx@4.23.15)(yaml@2.9.1))
```

After `pnpm install`, root `pnpm build` and `pnpm test` include the package via turbo.
