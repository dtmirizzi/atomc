# Converge with the swarm

::: info Planned
`atomc converge` and the swarm harness are **planned** for Phase 3. This page describes the target
behaviour defined by the [agent protocol contract](/architecture/contracts/agent-protocol) and
[PLAN §3](/plan/master).
:::

A build tells you what failed. **Convergence** is the loop that fixes it.

```bash
atomc converge --max-cost 2.00
```

## The loop

Each swarm agent runs an in-process state machine:

```
IDLE → PLAN → CLAIM_LOCK → ACT → VERIFY → RELEASE → (FAIL? ESCALATE)
```

1. **Wake.** A gate returns `FAIL` with an `owner_agent`. That agent is woken with the failure.
2. **Read.** The agent reads the IR subtree it owns at the current revision.
3. **Lock.** It calls `ir.lock(scope, holder, ttl_s, reason)` to claim the subtree exclusively.
4. **Act.** It makes changes through `tools.call` and `ir.transact(path, base_rev, ops)`.
5. **Verify.** It re-runs the affected DAG nodes and its own gates.
6. **Release.** On `PASS`, it unlocks and reports. On `FAIL`, it retries within its turn and budget
   caps, then escalates to the coordinator.

Conflicts (`ConflictError`) are handled by re-reading, rebasing, and retrying. A change that crosses
lock scopes becomes a `request` to the coordinator, which wakes the owning agent.

## Who owns what

| Agent | Lock scope | Fixes |
| ----- | ---------- | ----- |
| `ee-agent` | `/electrical`, `/layout`, `/keyboard` | ERC, assertions, test pads, matrix wiring, USB CC pulldowns |
| `fw-agent` | `/firmware`, `/simulation` | QMK compile, boot banner, matrix scan |
| `mech-agent` | `/mechanical` | plate cutouts, case USB cutout, pogo spacing, collisions |
| `ops-agent` | `/sourcing`, `/fabrication`, `/orders` | BOM stock, cost, lead time, fab quotes |

## Guards

- **Budget cap** — `--max-cost` caps model spend; the harness stops when it is hit.
- **Turn caps** — each agent has a bounded number of attempts before escalating.
- **Transcripts** — every session is written to `.atomc/sessions/<run>/<agent>.jsonl`.
- **Fake provider in CI** — a scripted pi-ai provider proves the loop converges deterministically;
  recorded real-model sessions replay nightly with a hard cost cap. See
  [Testing](/architecture/testing).
