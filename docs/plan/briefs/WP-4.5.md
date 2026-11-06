# WP-4.5 `e2e-vertical-slice` — `atomc build` end to end on atomc-pad

Read `_common.md`, PLAN §§1, 4, 6, 8, 9; the plugin handoffs (WP-4.1, WP-4.2, WP-4.2b, WP-4.3); the daemon DAG/plugin-discovery code; the WP-3.10 real-daemon harness (`tests/swarm/ts/harness.ts`) as the process-spawn pattern. This is the milestone test: the daemon discovers the four plugins and the project IR, runs the DAG, and gates evaluate against real IR state.

## Owned paths
- `tests/e2e/**` (new directory: harness + specs)
- `tests/e2e/package.json`, `tsconfig.json`, `vitest.config.ts`
- `tests/e2e/README.md`
- `docs/plan/handoffs/WP-4.5.md`

Do not edit root workspace/lockfile/CI, packages, plugins or examples. Request workspace/CI wiring in the handoff (exact commands).

## Deliverables
1. Real-process E2E harness: temp project dir seeded from `examples/atomc-pad` (system_ir.json + plugin symlink/copy so the daemon's project-tree discovery finds the four plugins, or entry-point discovery if the workspace install exposes them), spawn `atomcd serve`, drive through the real `@atomc/daemon-client`.
2. Vertical slice spec: request a DAG run covering the plugin-owned nodes; assert: all four plugins load (no `loaded=false` errors), pure gates evaluate against the seeded IR with real outcomes (PASS/FAIL as the fixture data dictates — the pad fixture should yield deterministic PASS/SKIP results recorded exactly), qmk.compile and renode_boot SKIP honestly when the toolchains are absent, and the IR is unchanged where no plugin writes. No fabricated PASS anywhere.
3. A second spec asserting failure honesty: mutate the seeded IR (e.g. a single-pin net) and assert `erc.no_unconnected` returns FAIL with evidence from the daemon.
4. Determinism and teardown rules identical to WP-3.10 (ephemeral port, temp trees, finally-safe stop, process-death assertion, no network beyond loopback).
5. README describing the layer; handoff with exact commands, expected outcomes per gate, deviations, and the workspace/CI request.

## Definition of done
- `tests/e2e` passes twice consecutively on a clean checkout with no external toolchains installed (SKIP paths), on Node 22 and 25.
- Every asserted gate outcome traces to daemon gate results read over RPC.
- Conventional commits; push `wp/4.5-e2e-vertical-slice`; do not merge.

## Stop and ask
If the daemon cannot run the four plugins' DAG nodes in one project (discovery or DAG-wiring gap), stop and report the exact seam rather than driving plugins directly.
