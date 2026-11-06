# WP-3.8 `studio-telemetry` — matrix-scan timing diagram and console stream

Read `_common.md`, PLAN §§1, 4, 6, 8, 9 and `docs/architecture/contracts/gate-result.md`. The daemon RPC exposes no telemetry: matrix-scan events and console output are not streamed today. PR #12 established the honesty pattern (`dataMode` + telemetry notices). This package renders telemetry-shaped data deterministically and honestly.

## Owned paths
- `apps/atomc-studio/src/telemetry/**` (timing diagram, console stream, event fixtures/types)
- `apps/atomc-studio/src/model.ts` (additive only)
- `apps/atomc-studio/src/studio-app.tsx` (**minimal edits only**: one nav item + one view render line)
- `apps/atomc-studio/test/telemetry.test.tsx`, `apps/atomc-studio/e2e` (add your own spec file only)
- `apps/atomc-studio/README.md` (one Views bullet)
- `docs/plan/handoffs/WP-3.8.md`

Do not edit root workspace/lockfile/CI, other packages or existing specs. No new runtime dependencies (hand-roll the SVG timeline; do not add a wavedrom package).

## Deliverables
1. Timing diagram (`telemetry/ScanTimeline.tsx` + `scan-events.ts`): render matrix-scan events (row/column strobes, key-down/up windows) as an accessible SVG timeline with labeled rows; pure event-model + layout functions are unit-tested (row assignment, time scaling, window bounds). WaveDrom-style semantics, hand-rolled rendering.
2. Console stream (`telemetry/ConsoleStream.tsx`): append-only log view (mono, timestamps, source badge per line: renode/qmk/renode-agent), virtualized or capped (bounded buffer, e.g. 500 lines, documented), with pause/clear controls that are keyboard operable.
3. Data sourcing is honest: in demo mode, deterministic fixture events clearly labeled simulated (reuse the `dataMode` notice pattern). In daemon mode, the view reports "Matrix-scan and console telemetry are not exposed by the daemon RPC yet" — an unavailable notice, not a spinning fake. Structure the API seam (`TelemetrySource` interface) so a future RPC method can plug in without UI changes.
4. A11y: the timeline exposes a text alternative table of the same events (screen-reader equivalent); the console is an aria-live region with polite politeness settings for new lines only when unpaused. Axe stays clean.
5. Tests: unit tests for event model, layout math, rendering with fixtures, capped buffer behavior, pause/clear interaction; one e2e spec asserting labels and operability; existing tests stay green; coverage floor holds.
6. Handoff with exact commands, design decisions, deviations, root changes needed (should be none).

## Definition of done
- `pnpm --filter @atomc/studio test`, `test:coverage:strict`, `typecheck`, `lint`, `build` pass; your e2e spec passes.
- No simulated data presented as live: demo fixtures labeled, daemon mode unavailable, no timestamps invented beyond fixture data.
- Conventional commits; push `wp/3.8-studio-telemetry`; do not merge.

## Stop and ask
If an accessible SVG timeline cannot pass axe in Chromium, or fixture event shapes conflict with `examples/atomc-pad/system_ir.json` matrix data, stop and report.
