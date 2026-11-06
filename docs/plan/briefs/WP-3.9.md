# WP-3.9 `studio-gates-orders` — full gate board and BOM/quote/orders tables

Read `_common.md`, PLAN §§1, 2, 4, 6, 8, 9 and `docs/architecture/contracts/{gate-result,plugin-manifest,ir-schema}.md`. Gate results are real daemon RPC data. BOM/quote/order data exists only as IR nodes and planned plugins — no sourcing/fab/orders plugin is implemented. PR #12 established the honesty pattern; this package extends it.

## Owned paths
- `apps/atomc-studio/src/board/**` (gate board)
- `apps/atomc-studio/src/sourcing/**` (BOM/quote/orders tables)
- `apps/atomc-studio/src/model.ts` (additive only)
- `apps/atomc-studio/src/studio-app.tsx` (**minimal edits only**: nav items + view render lines)
- `apps/atomc-studio/test/{board,sourcing}.test.tsx`, `apps/atomc-studio/e2e` (add your own spec file only)
- `apps/atomc-studio/README.md` (Views bullets)
- `docs/plan/handoffs/WP-3.9.md`

Do not edit root workspace/lockfile/CI, other packages, the existing gates table component or existing specs. No new runtime dependencies.

## Deliverables
1. Gate board (`board/GateBoard.tsx`): all gates grouped by owning domain (ee/fw/mech/ops via `owner_agent`), severity/status filter chips (blocking/advisory × pass/fail/skip/error), per-group pass-rate bars, and drill-in detail rows rendering real `GateResult` fields (evidence refs, suggestions, duration, ir_rev, evaluated_at). Unowned gates group under "Unowned" with a coordinator-review note, never silently dropped.
2. Sourcing tables (`sourcing/**`): BOM table (mpn, footprint, quantity, stock status, unit/extended cost) and quotes/orders tables (vendor, qty, unit cost, lead time, status), rendered from IR `/sourcing`-subtree data when present. When absent (the current real case), render an honest unavailable notice: "Sourcing and fabrication plugins are not implemented; no BOM, quote or order data exists." No fabricated rows, no fake totals, no order actions enabled.
3. Data derivation is pure and tested (`board/derive.ts`, `sourcing/derive.ts`): grouping, filter predicates, rate math, IR-node → table rows, empty-input behavior. Demo fixture extends `createDemoSnapshot` with clearly-labeled sample rows (same `dataMode` notice pattern).
4. A11y: tables have captions/scope headers; filters are keyboard-operable with announced counts; axe stays clean. Keyboard flow matches the existing views.
5. Tests: unit tests for derivation + rendering (fixtures, filters, empty states, unowned grouping); one e2e spec asserting the board renders real gate data from the demo snapshot and sourcing shows the unavailable notice; existing tests stay green; coverage floor holds.
6. Handoff with exact commands, design decisions, deviations, root changes needed (should be none).

## Definition of done
- `pnpm --filter @atomc/studio test`, `test:coverage:strict`, `typecheck`, `lint`, `build` pass; your e2e spec passes.
- Every number on screen traces to a `GateResult` or IR node or is labeled simulated; no invented BOM/quote/order data.
- Conventional commits; push `wp/3.9-studio-gates-orders`; do not merge.

## Stop and ask
If the IR schema's `/sourcing` node shape in `examples/atomc-pad/system_ir.json` differs from your expectations, stop and report rather than coercing rows.
