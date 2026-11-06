# Converge with the swarm

::: info Current status
The deterministic harness core is implemented with an injected provider port, scoped locks, transactions, budgets and gate-driven verification. Specialist definitions and a pi-ai adapter are pushed on WP-3.3 for review; the `converge` CLI command remains a structured stub while WP-3.4 implements the coordinator. This page describes the intended workflow defined by the [agent protocol contract](/architecture/contracts/agent-protocol) and [PLAN §3](/plan/master).
:::

The intended convergence loop routes each failed gate to a bounded, transactional specialist run.

```bash
atomc converge --max-cost 2.00
```

## The loop

The harness core implements one provider-injected transactional agent state machine:

```
IDLE → PLAN → CLAIM_LOCK → ACT → VERIFY → RELEASE → (FAIL? ESCALATE)
```

1. **Route (planned).** A gate can identify its `owner_agent`; the specialist registry/router that wakes it has not landed.
2. **Read.** The harness reads the declared IR scopes at their current revisions.
3. **Lock.** The harness calls `ir.lock(scope, holder, ttl_s, reason)` before any work.
4. **Act.** An injected provider may propose a schema-checked tool call or scoped patch; the harness sends it through `tools.call` or `ir.transact(path, base_rev, ops).`
5. **Verify.** The harness re-runs the configured DAG targets and owned gates.
6. **Release.** Locks are released on every terminal path. Actual gate results determine `PASS`; bounded blockers yield `RETRY` or `ESCALATE`. `atomc converge` does not yet schedule these runs.

Conflicts (`ConflictError`) trigger a fresh scoped read and model turn, never a stale patch resend. Cross-scope request routing belongs to the future convergence coordinator.

## Who owns what

| Specialist (planned registry) | Intended lock scope                    | Intended domain               |
| ----------------------------- | -------------------------------------- | ----------------------------- |
| `ee-agent`                    | `/electrical`, `/layout`, `/keyboard`  | ERC, test pads, matrix wiring |
| `fw-agent`                    | `/firmware`, `/simulation`             | QMK build and firmware checks |
| `mech-agent`                  | `/mechanical`                          | case, plate and jig checks    |
| `ops-agent`                   | `/sourcing`, `/fabrication`, `/orders` | BOM availability and quotes   |

## Guards

- **Budget cap** — the convergence core enforces aggregate cost/token/turn caps; the CLI's `converge --max-cost` passes them to an injected runtime (no runtime is bundled, so the command reports `unavailable`, exit 3).
- **Turn caps** — each run has a bounded number of provider decisions before escalation.
- **Transcripts** — every session is written to `.atomc/sessions/<run>/<agent>.jsonl`.
- **Fake provider in CI** — a scripted provider exercises the transaction/verification core without network calls. A real pi-ai adapter, recorded-session replay and capped live-model tests have not landed yet. See [Testing](/architecture/testing).
