# Swarm harness

When a gate fails, somebody has to fix it. atomc's fixer is a small swarm of domain agents running
**in-process** inside `packages/swarm-harness` (TypeScript, on top of
[`@mariozechner/pi-ai`](https://github.com/mariozechner/pi-ai)) — not a fleet of spawned CLIs.

## The state machine

```
IDLE → PLAN → CLAIM_LOCK → ACT → VERIFY → RELEASE → (FAIL? ESCALATE)
```

| State | What happens |
| ----- | ------------ |
| `PLAN` | The agent is woken with a `GateResult` whose `owner_agent` is itself, plus the IR subtree at a revision |
| `CLAIM_LOCK` | `ir.lock(scope, holder, ttl_s, reason)` claims the subtree for `agent:<name>#<session-seq>` |
| `ACT` | The agent calls plugin tools via `tools.call` and writes through `ir.transact(path, base_rev, ops)` |
| `VERIFY` | The affected DAG nodes are re-run (`dag.run`) and the agent's gates are re-checked (`gates.run`) |
| `RELEASE` | On `PASS`, unlock and report. On `FAIL`, retry within turn/budget caps, then escalate |

## Domains and lock scopes

| Agent | Lock scope |
| ----- | ---------- |
| `@ee-agent` | `/electrical`, `/layout`, `/keyboard` |
| `@fw-agent` | `/firmware`, `/simulation` |
| `@mech-agent` | `/mechanical` |
| `@ops-agent` | `/sourcing`, `/fabrication`, `/orders` |

Cross-scope changes are not made directly. The agent posts a **request** to the coordinator, which
wakes the owning agent instead. This keeps a single writer per subtree.

## Conflict handling

Because transactions carry a `base_rev`, two agents cannot silently clobber each other. A stale write
raises `ConflictError(current_rev)`; the agent re-reads, rebases and retries. Locked subtrees raise
`LockedError(holder, expires_at)`.

## Budgets and transcripts

- `atomc converge --max-cost <usd>` caps model spend.
- Turn caps bound how many attempts an agent makes before escalating.
- Every session is written to `.atomc/sessions/<run>/<agent>.jsonl`.
- The same machinery runs under a deterministic **fake LLM** in CI (scripted pi-ai provider) to prove
  convergence, lock contention and rollback; recorded real sessions replay nightly with a hard cap.

The full protocol is frozen in the
[agent protocol contract](/architecture/contracts/agent-protocol).
