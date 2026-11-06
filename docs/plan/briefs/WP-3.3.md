# WP-3.3 `harness-agents` — specialist definitions and provider adapter

Read `_common.md`, PLAN §§0, 1, 4, 6, 8, 9; `docs/architecture/contracts/{agent-protocol,rpc,gate-result,plugin-manifest}.md`; the `@atomc/swarm-harness`, daemon-client and plugin-sdk READMEs. WP-3.2 is merged and implements the deterministic transactional loop. Use its public API; don't duplicate it.

## Goal

Provide the four domain specialists and a usable provider adapter while keeping routing, locks, tools, budgets and gate truth owned by the existing harness. Agent prompts must be domain-specific but careful not to invent hardware facts. Model output may propose changes only; daemon RPC validation and gates remain authoritative.

## Owned paths
- `packages/swarm-harness/ts/src/agents/**`
- `packages/swarm-harness/ts/src/providers/**`
- `packages/swarm-harness/ts/src/multimodal.ts` (image inspection support)
- `packages/swarm-harness/ts/src/types.ts` and `src/index.ts` (additive public API)
- `packages/swarm-harness/ts/src/runner.ts` (only signal/transcript/attachment plumbing needed by the adapter)
- `packages/swarm-harness/ts/test/agents.test.ts`
- `packages/swarm-harness/ts/test/providers/**`
- `packages/swarm-harness/ts/test/multimodal.test.ts`
- `packages/swarm-harness/ts/test/runner-multimodal.test.ts`
- `packages/swarm-harness/README.md`
- `docs/plan/handoffs/WP-3.3.md`

Keep the provider implementation under `src/providers/pi-ai.ts` and its tests under `test/providers/`. Do not change existing core runner behavior beyond forwarding the AbortSignal and accumulating actual model/tool turns plus inspection-image attachments into subsequent `ModelRequest`s. The deterministic `runAgent` state/lock/gate semantics remain unchanged.

Do not edit root files, lockfiles, CI, frozen contracts, daemon, CLI, or Studio. If catalog/root integration is needed, list exact requirements in the handoff.

## Deliverables
1. Registry with definitions for `ee-agent`, `fw-agent`, `mech-agent`, `ops-agent`: clear prompt, ownership scopes, manifest `produces` scopes, relevant gates/DAG targets, explicit tools, model routing and conservative per-run caps. Expose lookup/list APIs; reject duplicate IDs and invalid scope/tool/budget config.
2. Prompts include the required decision discipline: cite the provided IR/evidence, do not guess pins/parts/measurements, request clarification or cross-scope help, never claim PASS, use only permitted tools, keep changes minimal, and surface risks. Use real example facts from committed atomc-pad/keeb fixtures only as examples, not as global defaults.
3. Provider adapter for `@mariozechner/pi-ai` v0.73.x behind `ModelProvider`. Map `ModelRequest` (including transcript/previous tool results and image attachments) to pi-ai, map tool/patch/verify/give-up output into `ModelDecision`, map usage cost/tokens, forward `AbortSignal` to pi-ai, and emit no credentials or raw secrets to logs/transcripts. If pi-ai's current API cannot safely support this, stop and report the exact blocker rather than shipping a pseudo-adapter.
4. Provider configuration and construction take injected env/secrets/transport through a safe factory/config seam. Default keys come from environment/config secret references, never serialized `AgentDefinition` or browser URLs. No API key is required in tests.
5. Tests: registry completeness and rejection cases; each agent gate/tool/scope policy; prompt safety/invariants; deterministic provider mapping with a mocked pi-ai transport; malformed model output; usage accounting; AbortSignal; secret redaction; error mapping. No live API calls.
6. Image inspection is filesystem-safe: inputs are project-relative, traversal/absolute paths and symlink escapes are rejected, with injectable bounded reader for tests/hosts.
7. README explains how to choose provider/model, configure keys safely, inspect the registry, cap cost/tokens/turns, and run tests offline; direct integration examples are type-compatible with pi-ai v0.73.x.

## Definition of done
- `pnpm --filter @atomc/swarm-harness test`, `test:coverage`, `typecheck`, `lint`, `build`
- Coverage remains ≥85% statements/branches/lines/functions for harness source (do not exclude substantive agent/provider code).
- `pnpm exec biome check packages/swarm-harness/ts/src packages/swarm-harness/ts/test`
- `pnpm exec turbo run build test typecheck` after root lock importer integration
- Handoff records exports, provider API mapping, secret flow, exact tests, caveats and lock importer if any.
- Conventional commits on `wp/3.3-harness-agents`, push branch. No merge; orchestrator reviews.

## Stop and ask

Ask the orchestrator if a contract ambiguity arises, if a new dependency outside PLAN §2 is needed, or if pi-ai cannot be wired as a real adapter without making unsafe assumptions. No vendor API keys are available; all provider tests must use a mock transport.
