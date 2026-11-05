# WP-3.2 `harness-core` — transactional swarm state machine (fake LLM first)

Read `_common.md`, PLAN §§1, 4, 5, 6, 8, 9, `docs/architecture/contracts/{agent-protocol,rpc,gate-result,ir-schema}.md`, and the pi-ai API usage in `@atomc/plugin-sdk` / cached installed `@mariozechner/pi-ai` package docs only if needed. Do not build a generic chat loop: implement the transaction and verification state machine from the frozen contract. No live provider calls in this WP.

## Owned paths
- `packages/swarm-harness/ts/**`
- `packages/swarm-harness/README.md`
- `docs/plan/handoffs/WP-3.2.md`

Do not edit daemon/client/plugin-sdk/CLI/root files/contracts. If SDK exports are missing, report requirements in handoff.

## Deliverables
1. Package `@atomc/swarm-harness` (ESM+DTS, tsup/Vitest, catalog `@mariozechner/pi-ai`, `@mariozechner/pi-agent-core`, zod, vitest, TypeScript, daemon-client, core-ir; use workspace dependencies). Create a narrow injectable provider interface; tests use only a scripted fake, no API keys/network.
2. Typed protocol: `AgentDefinition` (id, system prompt, permitted tools, lock scopes, model config), `AgentSession`, `GateFailure`, `AgentTurn`, `AgentPatchProposal`, `SwarmEvent`, session metadata. Keep secrets out of serialized logs.
3. Explicit state machine: `IDLE → PLAN → CLAIM_LOCK → ACT → VERIFY → RELEASE → (PASS/RETRY/ESCALATE)`. Every exit/error/abort path releases acquired locks in `finally`; optimistic conflict causes bounded re-read/replan, not blind resend. Domain agent may write only its assigned IR subtrees and declared plugin `produces` scopes.
4. `runAgent` loop: receive scoped failure/context, read relevant IR via daemon client, ask injected model adapter for tool/patch calls, validate tool schema and allow-list, acquire per-node locks, apply only transactions with current `_meta.rev`, trigger targeted DAG run and verification gates, retry bounded by max turns/budget, escalate on persistent blockers. Agents never self-report success: convergence reads actual gate results.
5. Persistent transcripts in project `.atomc/sessions/<run>/<agent>.jsonl` using atomic append/rotation; record inputs/tool calls/results/gates/cost metadata with redaction hooks, omit bearer tokens/datasheet secrets by default.
6. Cost/turn/token limits and abort signal; deterministic `FakeProvider` that scripts success/failure/conflict/tool cycles; optional pi-ai provider adapter lives behind interface and is not invoked by tests.
7. Tests cover state transitions, lock release on all paths, conflict retry, rollback, tool allow-list, gate-driven verification, bounded retries/escalation, abort, fake-provider transcripts, budget cap/redaction. No live OpenRouter calls.
8. README explains how CLI (WP-3.1) and specialists register agents, configure providers/models, cap spend, and replay tests.

## Definition of done
`pnpm --filter @atomc/swarm-harness test typecheck lint build`, coverage ≥85%, `pnpm exec biome check packages/swarm-harness/ts`, and root turbo build/test passes after root importer integration. Handoff with the public API, state diagram, exact tests, and root lock importer requirements; commit/push `wp/3.2-harness-core`.
