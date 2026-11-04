# Contract: Swarm agent protocol (v0.1) — draft, frozen at Phase 3 start

Agents: `ee-agent` (lock scope `/electrical`, `/layout`, `/keyboard`), `fw-agent` (`/firmware`, `/simulation`),
`mech-agent` (`/mechanical`), `ops-agent` (`/sourcing`, `/fabrication`, `/orders`). Holder id:
`agent:<name>#<session-seq>`.

Loop: wake(GateResult FAIL with owner_agent=me) → read IR subtree (rev) → plan → `ir.lock` scope →
act via `tools.call` / `ir.transact(base_rev)` → `dag.run` affected → `gates.run` owned gates →
PASS → unlock + report; FAIL → retry (≤ N turns, ≤ budget) → escalate to coordinator.
Conflict → re-read, rebase, retry. Cross-scope change needed → post a `request` to the coordinator,
which wakes the owning agent. All transcripts → `.atomc/sessions/<run>/<agent>.jsonl`.
