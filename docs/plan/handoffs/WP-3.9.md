# WP-3.9 handoff — studio-gates-orders

Branch: `wp/3.9-studio-gates-orders` · Owner: pi / DeepSeek Flash · Base: `main` @ `4ba3bdb`

## What was built

A full gate board and read-only sourcing/BOM/quote/order tables for Studio, plus pure,
tested derivation and one Playwright spec. All numbers on screen trace to a `GateResult`, an IR
node, or are labeled as simulated.

### Gate board — `apps/atomc-studio/src/board/**`

- `derive.ts` (pure): `domainOf`, `groupGates`, `filterGates`, `countByStatus`, `countBySeverity`,
  `passRate`, `gateTitle`, `formatDuration`, `formatTimestamp`, `elementIdFor`.
- `GateBoard.tsx`: every gate grouped by `owner_agent` domain (`ee`/`fw`/`mech`/`ops`) with an
  explicit **Unowned** group for `owner_agent: null` and a coordinator-review note (never dropped).
  Severity chips (any/blocking/advisory) and result chips (any/PASS/FAIL/SKIP/ERROR) with live
  counts and a `role="status"` announcement of "Showing X of Y gates". Per-group pass-rate bar
  (`role="progressbar"`) and blocking-failure flag. Each row expands to a drill-in rendering the
  real `GateResult`: id, plugin, `ir_rev`, `duration_ms`, `evaluated_at`, severity, summary,
  evidence (`kind`, `ref`, `message`, JSON `data`), suggestions (message + patch path/op count) and
  `refs`.
- `board.css`: scoped styles (reuses existing theme vars/classes; no edits to `src/styles.css`).

### Sourcing tables — `apps/atomc-studio/src/sourcing/**`

- `types.ts`: structural read-only subsets of IR `/sourcing`, `/fabrication`, `/orders` (contract
  ir-schema.md §4.7–4.9) plus a minimal `ComponentSummary` for footprint joins.
- `derive.ts` (pure): `selectOffer`, `unitPriceMinor` (largest price break ≤ quantity, falling back
  to the smallest), `stockStatus`, `stockLabel`, `formatMoney`, `buildQty`, `deriveBomRows`,
  `deriveQuoteRows`, `deriveOrderRows`, `sourcingAvailability`, and the notice strings.
- `SourcingView.tsx`: BOM table (MPN, footprint, qty, stock status + on-hand, unit cost, extended
  cost, lead time), fabrication quote table and orders table. Renders only from IR data that is
  present. When a project has no supply-chain data at all (the normal case today — no sourcing,
  fabrication or orders plugin is implemented) it renders the exact notice
  "Sourcing and fabrication plugins are not implemented; no BOM, quote or order data exists."
  Missing sections render per-section "not implemented" notices. No order actions, no fabricated
  rows or totals.

### Wiring

- `model.ts` (additive): `BoardSnapshot` gains optional `sourcing`, `fabrication`, `orders`,
  `components`; `createDemoSnapshot` gains clearly-labeled sample BOM/component rows and evidence
  on the failing matrix-scan gate.
- `studio-app.tsx` (minimal): two nav items (`Gate board`, `BOM & orders`) and their view render
  lines. Existing `Gate results` / `GateTable` are untouched.
- `README.md`: added **Gate board** and **BOM & orders** view bullets.

### Tests

- `test/board.test.tsx` — derivation + rendering: domain grouping, unowned group, counts, pass
  rates, severity/status filters (incl. keyboard toggle), drill-in fields, demo/empty states,
  Studio-shell navigation.
- `test/sourcing.test.tsx` — derivation (offer/price/stock/money/quantity/footprint joins) and
  rendering (BOM rows, per-section and combined notices, quote/order tables, simulated/daemon
  labels, no order actions, Studio-shell navigation).
- `e2e/gates-orders.spec.ts` (new) — board renders real demo gate data and expands detail;
  sourcing shows labeled sample rows plus the honest unavailable notices; axe WCAG 2.1 A/AA clean
  on both views.

Coverage (strict): statements 92.36 %, branches 88.28 %, functions 88.69 %, lines 92.3 % — above
the 80/75/75/80 floor. 59 unit tests + 10 Playwright tests pass.

## How to verify (exact commands)

```bash
# build workspace deps Studio imports first (daemon-client dist types)
pnpm --filter @atomc/core-ir build
pnpm --filter @atomc/daemon-client build

pnpm --filter @atomc/studio test
pnpm --filter @atomc/studio test:coverage:strict
pnpm --filter @atomc/studio typecheck
pnpm --filter @atomc/studio lint
pnpm --filter @atomc/studio build
pnpm --filter @atomc/studio e2e
```

## Design decisions

- **New nav items rather than replacing the existing gates view.** The existing `Gate results` view
  (flat `GateTable`) and its specs are owned by WP-3.6 and must not change; the grouped `GateBoard`
  is added as `Gate board`, reachable alongside it. This keeps the existing unowned-gate fallback
  test green while the board implements the required explicit "Unowned" grouping.
- **Honest notices are section-aware.** A single "nothing exists" notice is shown when the whole
  supply chain is empty. When some data exists (e.g. the demo BOM), each empty section gets its own
  "not implemented" notice so the copy is never false (it does not claim the BOM is missing when it
  is present). The demo fixture carries a BOM but no quotes/orders, so the e2e can assert the
  unavailable notice while the BOM table is visible.
- **Footprint join is optional.** `/sourcing` has no footprint field; it is joined from
  `/electrical/components` when a component index is available, otherwise shown as "Not in IR"
  rather than coerced.
- **Derivation is pure and framework-free** in `board/derive.ts` / `sourcing/derive.ts`, so all
  grouping/filtering/rate/row math is unit-tested without React.

## Deviations from contract

None. Data shapes follow `docs/architecture/contracts/ir-schema.md` §4.7–4.9 and
`gate-result.md`; `GateResult` is consumed from `@atomc/daemon-client` unchanged.

## Open issues

- `daemon-api.ts` (not owned by this WP) does not surface IR `/sourcing`, `/fabrication` or
  `/orders` into `BoardSnapshot`, so a live daemon snapshot currently renders the honest
  "unavailable" notice even if a future project had that data. Wiring the IR subtrees into
  `createDaemonStudioApi` is a small follow-up (additive `BoardSnapshot` fields already exist).
- Supply-chain tables are read-only by design; no creation/mutation UI exists.

## Root changes needed

None.
