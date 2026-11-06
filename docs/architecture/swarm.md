# Swarm harness

When a gate fails, the responsible specialist should fix it. The deterministic transaction core is
implemented in `packages/swarm-harness` as a TypeScript library with an injected provider/daemon API.
The runner enforces locks, scopes, spend/turn limits, schema-checked tools and gate-driven outcomes.

The pushed WP-3.3 branch adds specialist definitions/prompts, gate routing, image inspection and a typed pi-ai adapter; it is awaiting review and lockfile integration. WP-3.4 is implementing convergence. CI continues to use offline fakes.

## The state machine

```
IDLE → PLAN → CLAIM_LOCK → ACT → VERIFY → RELEASE → (FAIL? ESCALATE)
```

| State        | What happens                                                                                            |
| ------------ | ------------------------------------------------------------------------------------------------------- |
| `PLAN`       | The agent is woken with a `GateResult` whose `owner_agent` is itself, plus the IR subtree at a revision |
| `CLAIM_LOCK` | `ir.lock(scope, holder, ttl_s, reason)` claims the subtree for `agent:<name>#<session-seq>`             |
| `ACT`        | The agent calls plugin tools via `tools.call` and writes through `ir.transact(path, base_rev, ops)`     |
| `VERIFY`     | The affected DAG nodes are re-run (`dag.run`) and the agent's gates are re-checked (`gates.run`)        |
| `RELEASE`    | On `PASS`, unlock and report. On `FAIL`, retry within turn/budget caps, then escalate                   |

## Domains and lock scopes

| Agent         | Lock scope                             |
| ------------- | -------------------------------------- |
| `@ee-agent`   | `/electrical`, `/layout`, `/keyboard`  |
| `@fw-agent`   | `/firmware`, `/simulation`             |
| `@mech-agent` | `/mechanical`                          |
| `@ops-agent`  | `/sourcing`, `/fabrication`, `/orders` |

Cross-scope writes are rejected by the harness. The future convergence coordinator is intended to route a request to the owning specialist; that routing is not implemented yet.

## Conflict handling

Because transactions carry a `base_rev`, two agents cannot silently clobber each other. A stale write
raises `ConflictError(current_rev)`; the harness re-reads current state before asking the provider for a new decision. It does not resend the stale patch. Locked subtrees raise `LockedError(holder, expires_at)`.

## Budgets and transcripts

- The harness accepts per-run cost, token and turn caps.
- Turn caps bound how many attempts an agent makes before escalating.
- Sessions written through `TranscriptWriter` go to `.atomc/sessions/<run>/<agent>.jsonl`.
- The deterministic core runs under a scripted `FakeProvider` in CI to verify state transitions,
  lock cleanup, schema-checked tool calls, conflict handling, budget caps and gate-based outcomes.
  Real-provider sessions/replay and capped live runs are future work.

The full protocol is frozen in the
[agent protocol contract](/architecture/contracts/agent-protocol).
