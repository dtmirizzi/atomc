# WP-3.8 — `studio-telemetry` handoff

Status: **complete.** The matrix-scan timing diagram and console stream are implemented,
unit-tested, e2e/axe-verified and wired into Studio as a new view. No root, contract,
lockfile or other-package change was needed. Specs match the example IR matrix blocks and
no fixture is presented as live data.

## What was built

All new code lives under the owned paths (`apps/atomc-studio/src/telemetry/**`,
`apps/atomc-studio/test/telemetry.test.tsx`, `apps/atomc-studio/e2e/telemetry.spec.ts`),
plus additive/minimal edits to `src/model.ts` (none needed in the end), `src/studio-app.tsx`,
`src/styles.css` and `README.md`.

### Timing diagram — `src/telemetry/scan-events.ts` + `ScanTimeline.tsx`

- Pure event model: `ScanEvent` (`row-strobe` | `col-strobe` | `key-down` | `key-up`),
  `MatrixSpec` and `ScanTimelineModel`. `ATOMC_PAD_MATRIX` and `ATOMC_KEEB_MATRIX` mirror the
  `keyboard.matrix` blocks of `examples/atomc-pad/system_ir.json` and
  `examples/atomc-keeb/system_ir.json` (rows/cols, row/col pin names, `diode_direction`).
- Pure layout math, each unit-tested: `buildLanes` (one lane per row signal, one per column
  signal, one shared key-event lane), `laneForEvent`, `eventWindow` (clamped window bounds),
  `scaleTime` (linear time→x, clamped) and `layoutTimeline` (lane y positions, bar x/width,
  time ticks).
- `createDemoScanModel` is deterministic (no wall-clock reads): each cycle selects every row
  in turn, samples every column while the row is active, and records key-down/up windows for
  the pressed keys.
- `ScanTimeline.tsx` renders a hand-rolled, WaveDrom-style SVG (`role="img"` with `<title>`/
  `<desc>`) plus a scrollable, keyboard-focusable event table that is the screen-reader text
  alternative. No new dependency was added.

### Console stream — `src/telemetry/console-stream.ts` + `ConsoleStream.tsx`

- `ConsoleLine` carries a source badge (`renode` | `qmk` | `renode-agent`), level and an
  ISO timestamp **supplied by the producer**. `formatConsoleTimestamp` only reformats it.
- `ConsoleBuffer` is a bounded FIFO: hard cap `CONSOLE_BUFFER_LIMIT = 500`, drops oldest first
  and reports `droppedCount`; `visible()` renders the latest `CONSOLE_VIEW_LIMIT = 200`.
- `ConsoleStream.tsx` is an append-only `role="log"` view (mono, timestamps, source badges)
  with native Pause/Resume and Clear buttons. The live region is `aria-live="polite"` while
  unpaused and `aria-live="off"` while paused; pausing keeps the frozen snapshot visible,
  buffers new lines and shows a status message.

### Honest sourcing — `src/telemetry/source.ts` + `TelemetryView.tsx`

- `TelemetrySource` is the API seam: `mode`, `load(): Promise<TelemetryBundle>` and
  `subscribe(line => …): () => void`. A future daemon `telemetry.subscribe` RPC method can
  implement it without touching the view.
- `createDemoTelemetrySource` returns labeled fixtures (`TelemetryNotice.kind = "demo"`,
  "Simulated telemetry…") and `createDaemonTelemetrySource` returns `scan: null`, an empty
  console and the notice "Matrix-scan and console telemetry are not exposed by the daemon RPC
  yet." The view reuses the existing `dataMode`/telemetry-notice honesty pattern — no fake
  spinner, no invented timestamps.
- `TelemetryView` owns the buffer and pause/freeze state and is wired into `studio-app.tsx`
  with the minimum allowed edits: one `ViewId` member, one nav item and one render line.

### Tests

- `test/telemetry.test.tsx` — 27 tests: event model, deterministic fixtures, lane assignment,
  window clamping, time scaling, layout geometry/ticks, buffer cap/drop/clear/limit
  validation, timestamp formatting, both sources, SVG/table rendering, console
  announcements and controls, demo/daemon views, pause-freeze/resume, clear, loading/error.
- `e2e/telemetry.spec.ts` — 3 Playwright tests: labeled demo capture + operability, keyboard
  pause/clear, and an axe WCAG 2.1 A/AA serious/critical check on the telemetry view.
- Existing 30 unit tests and 5 e2e specs stay green.

## How to verify (exact commands)

From the repository root:

```bash
pnpm install --frozen-lockfile
# workspace deps are consumed as built packages:
pnpm --filter @atomc/core-ir build
pnpm --filter @atomc/daemon-client build

pnpm --filter @atomc/studio test               # 57 tests (3 files)
pnpm --filter @atomc/studio test:coverage:strict
pnpm --filter @atomc/studio typecheck
pnpm --filter @atomc/studio lint
pnpm --filter @atomc/studio build
pnpm --filter @atomc/studio e2e:install        # first run only
pnpm --filter @atomc/studio e2e                # 8 specs
```

Measured on this branch: coverage `92.19%` statements / `88.85%` branches / `85.61%`
functions / `92.28%` lines (telemetry module alone: 98.9% stmts). `pnpm --filter @atomc/studio
lint` exits 0 (30 pre-existing CSS `noDescendingSpecificity` warnings, no errors).

## Design decisions

- **Microseconds, not milliseconds.** Real matrix scan strobes are tens of microseconds, so
  scan events use `atUs`/`durationUs` and the axis is labelled in µs. Console lines keep the
  producer's ISO timestamp.
- **Row-select semantics.** The diagram shows each row selected in turn with columns sampled
  while the row is active. It labels the IR `diode_direction` value but does not claim to prove
  which pin is driven, so it stays true for both diode directions.
- **Lane reuse for key events.** Row strobes live in per-row lanes, column samples in per-column
  lanes, and key-down/up windows share one "Key events" lane keyed by `row`/`col`, avoiding one
  lane per key.
- **Scroll regions are focusable.** Axe's `scrollable-region-focusable` rule requires it; the
  two scroll containers use `tabIndex={0}` with an accessible label and a targeted
  `biome-ignore`. This is the only lint suppression added.
- **Bounded, honest console.** Hiding history silently would be dishonest, so the view reports
  how many lines rolled off. Pause freezes the view but keeps buffering, and says so.

## Deviations from contract

None. `gate-result.md` is not implicated by this view. No root files changed.

## Open issues

- The daemon RPC still exposes no matrix-scan/console telemetry, so daemon mode intentionally
  shows an unavailable notice. The `TelemetrySource` seam is ready for a future RPC method;
  wiring it is out of scope here (and would require the daemon/contracts owners).
- The timing diagram is a fixture capture illustrating scan semantics; it is not proof of
  Renode or USB HID behavior.

## Root changes needed

None.
