# WP-3.5 `harness-tests` — contract replay and end-to-end convergence assurance

Read `_common.md`, PLAN §§4, 6, 8, 9 and the frozen agent/RPC/gate contracts. Inspect WP-3.2, WP-3.3 and WP-3.4 handoffs before defining this package's seams. Tests use real daemon/client code only where deterministic and credential-free; model calls always use fakes/recordings. Vendor keys and live model credentials are unavailable.

## Owned paths
- `tests/swarm/**`
- `packages/swarm-harness/ts/test/fixtures/**`
- `packages/swarm-harness/ts/test/conformance/**`
- `docs/architecture/testing.md` (only the swarm test row)
- `docs/plan/handoffs/WP-3.5.md`

Integration note: WP-3.3/3.4 own active harness tests and README work. Coordinate boundaries first. Add only cross-package replay/conformance tests under `tests/swarm/**` and fixtures to the fixture paths above; do not edit their active test files or README.

Coordinate package test-file ownership with WP-3.3/3.4. Do not edit root workspace, lockfile, CI, frozen contracts, daemon or client. Request CI changes from orchestrator in handoff.

## Deliverables
1. Stable recorded `ModelRequest`/`ModelDecision` fixtures with schema/version metadata, no secrets, and deterministic replay. Redact fixture generation; validate fixtures before use; document how to update them.
2. Conformance suite proving each specialist definition obeys frozen IDs, gate ownership, lock scopes, manifest produces/tools policies and budget constraints.
3. End-to-end test against daemon/client RPC with fixture plugins/fake provider covering failure -> routed agent -> checked patch/tool -> DAG/gates -> final gate state. Ensure repeat run determinism, optimistic conflict, lock cleanup and abort.
4. Property/fuzz tests for router/scheduler invariants and budgets, using stable seeds and bounded runtime. Do not turn property testing into flaky timing/load tests.
5. Test report utility that summarizes coverage, decisions, tool calls, gate transitions and minor-unit spend without leaking secrets. Avoid snapshots that include nondeterministic timestamps/paths.
6. CI request: add swarm contract task to Turbo/CI and upload useful test artifacts only when safe; specify exact job commands, needed services, and cost estimate. No live-provider job is required until credentials/approval exist.
7. Handoff with test layers, fixture format, exact commands, limitations and required root integration.

## Definition of done
- Deterministic fakes and recorded replays pass on Node 22 and 25.
- Cross-component integration passes on Linux; no vendor API keys, hardware, networked LLMs, or secrets needed.
- Standard TypeScript checks and Biome are clean; existing coverage floors remain intact.
- No flaky tests; all retry/time behavior is controlled by fake clock/transport.
- Conventional commits and push `wp/3.5-harness-tests`; do not merge.

## Stop and ask

Ask before changing contracts, adding CI services/dependencies, or storing any real-model transcript. Keep any later live-model test opt-in, budget-capped and separate from PR-required CI.
