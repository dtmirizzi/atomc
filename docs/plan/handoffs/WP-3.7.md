# WP-3.7 — `studio-3d` handoff

Status: **complete.** R3F board/plate viewer with test-pad overlay landed on
`wp/3.7-studio-3d`, branched from `main` at `18c1f64` (the Phase 3 completion
wave brief). All work is confined to owned studio paths; the only cross-boundary
file touched is `apps/atomc-studio/package.json` (allowed by the brief) plus the
orchestrator-owned `pnpm-lock.yaml`, which is intentionally **not** committed.

## What was built

| File | Responsibility |
|---|---|
| `apps/atomc-studio/src/viewer3d/geometry.ts` | Pure, three/WebGL-free derivation: `deriveViewerGeometry(raw) -> ViewerGeometry` (available \| unavailable). Board outline from `/layout/outline`, falling back to `/mechanical/pcb_bbox`; switch cutouts from `/keyboard/keys` on a 19.05 mm pitch using `mechanical.plate.cutout_mm`; test-pad markers from `/layout/test_pads`. `geometryCenter()` for renderer framing. |
| `apps/atomc-studio/src/viewer3d/BoardViewer.tsx` | R3F `<Canvas>` scene (PCB extruded outline + plate layer with real square cutout holes via `THREE.Shape` holes + test-pad cylinders on their declared side). Always renders an accessible `GeometrySummary` (bounds, outline source, cutout/pad counts, notices). Exports `makeOutlineShape`/`toSquareHole` for direct unit tests. |
| `apps/atomc-studio/src/viewer3d/webgl.ts` | Isolated `supportsWebGL()` probe so jsdom can be mocked and a WebGL-less browser degrades to the summary instead of throwing. |
| `apps/atomc-studio/src/viewer3d/Viewer3DView.tsx` | View wiring: derives geometry from `snapshot.systemJson`, renders the data-source banner (simulated / daemon IR / unavailable) and `BoardViewer`. |
| `apps/atomc-studio/src/viewer3d/fixtures.ts` | Demo IR subset mirroring `examples/atomc-pad/system_ir.json` (3×3 macropad, 80×80 board, 15 test pads). |
| `apps/atomc-studio/src/viewer3d/viewer3d.css` | Viewer styles (kept out of the unowned `styles.css`). |
| `apps/atomc-studio/src/model.ts` | Additive only: `BoardSnapshot.systemJson?: unknown`; the demo snapshot carries the fixture IR. |
| `apps/atomc-studio/src/studio-app.tsx` | Minimal edits only: `"viewer3d"` `ViewId`, one nav item, one render line, one import. |
| `apps/atomc-studio/test/viewer3d.test.tsx` | 22 new unit tests: derivation (bounds, cutout count/positions, y-flip mapping, pad mapping, mechanical fallback, defaults, malformed-input filtering, empty-input unavailable, centre), shape helpers, real WebGL probe, component wiring for demo/daemon/absent IR, and 3D nav integration. |
| `apps/atomc-studio/e2e/viewer3d.spec.ts` | Two Playwright specs (real Chromium, software WebGL): canvas renders with the honest source label and summary; axe WCAG 2.1 A/AA scan clean. |

No invented geometry: every switch/pad/outline value traces to an IR field; a
snapshot without a usable outline returns `unavailable`, and a snapshot without
system IR shows "Geometry unavailable" while the demo is labelled simulated.

## How to verify (exact commands)

From the repository root:

```bash
# deps + workspace build of the studio's TS dependencies (the lockfile is currently
# updated locally; the orchestrator owns the committed importer — see below)
pnpm install
pnpm --filter @atomc/daemon-client... build
pnpm --filter @atomc/studio build

pnpm --filter @atomc/studio test                     # 45 tests (23 pre-existing + 22 new)
pnpm --filter @atomc/studio test:coverage:strict     # thresholds hold
pnpm --filter @atomc/studio typecheck
pnpm --filter @atomc/studio lint
pnpm --filter @atomc/studio e2e                      # 7 specs incl. the 2 new ones

pnpm exec biome check apps/atomc-studio/src/viewer3d \
  apps/atomc-studio/src/model.ts apps/atomc-studio/src/studio-app.tsx \
  apps/atomc-studio/test/viewer3d.test.tsx apps/atomc-studio/e2e/viewer3d.spec.ts \
  apps/atomc-studio/package.json
```

Observed on this branch (Node 25.1.0, pnpm 10.30.3): 45/45 unit tests pass;
coverage 85.08% statements / 84.75% branches / 78.68% functions / 85.91% lines
(functions threshold is 70); `tsc --noEmit`, `biome check` and `vite build`
clean; 7/7 Playwright specs pass including the axe scan on the 3D view.

## Design decisions

- **Geometry derivation is pure and WebGL-free.** `geometry.ts` takes `unknown`
  (daemon JSON crosses a boundary) and narrows every field, so it is unit-testable
  in jsdom and reusable by any renderer. `three` is only imported by the view.
- **Plate cutouts are real holes.** The plate shape is built once with a square
  `THREE.Path` hole per switch, so the visible cutouts correspond 1:1 to
  `/keyboard/keys` rather than decorative markers.
- **Keyboard origin flip.** `ir-schema.md` puts the keyboard layout origin at
  top-left and the board frame at bottom-left, so switch `y` is mapped as
  `maxY - y_u·pitch - h_u·pitch/2`. This is documented in `geometry.ts` and
  asserted by unit tests.
- **The canvas is never the only representation.** `GeometrySummary` is rendered
  unconditionally and carries the bounds/counts/notices; the WebGL branch only
  adds the interactive scene. `supportsWebGL()` sits in its own module so tests
  exercise both paths with the real probe.
- **One honesty banner, mirroring the agents view.** `Viewer3DView` derives a
  `dataMode`-based source notice: demo → "Simulated geometry"; daemon with IR →
  "Daemon IR geometry … IR revision N"; daemon without IR → "Geometry
  unavailable".
- **`@types/three` added.** `three@0.187.0` ships no `.d.ts`, and the strict
  tsconfig needs it. It is a dev-only type package pinned to `^0.187.0` in the
  studio's `package.json` (see root changes).

## Deviations from contract

None. No frozen contract (`ir-schema.md`, `plugin-manifest.md`, RPC/gate/agent)
was changed; the viewer reads IR fields exactly as documented.

## Open issues

1. **Daemon mode does not yet receive IR from RPC.** `BoardSnapshot.systemJson`
   is wired and tested, but the unowned `apps/atomc-studio/src/daemon-api.ts`
   drops the `getIR("/")` value it already reads. Until that file (studio shell
   owner / orchestrator) sets `systemJson: ir.value`, real daemon snapshots show
   the honest "Geometry unavailable" notice. Demo geometry and the daemon
   rendering path are both fully implemented and tested via injected snapshots.
2. **Bundle size.** `three` + `@react-three/fiber` push the studio bundle to
   ~1.2 MB minified (~329 kB gzip). A follow-up could lazy-load the viewer route
   (`React.lazy` + dynamic import). Not required by the brief; build still passes.
3. **No orbit/drag controls.** The brief marks them optional. The camera is
   framed from the derived bounds and the summary covers accessibility; adding
   pointer controls would need `three/examples` OrbitControls or a small manual
   implementation and is deliberately left out to keep the e2e stable.

## Root changes needed (orchestrator-owned)

1. **`pnpm-lock.yaml`** — regenerate the `apps/atomc-studio` importer for the new
   deps (`@react-three/fiber`, `three` from the catalog, `@types/three`). Local
   `pnpm install` produced the diff; it is left uncommitted per `_common.md`.
2. **`pnpm-workspace.yaml` catalog (optional)** — add `'@types/three': ^0.187.0`
   so the studio's dev-dependency can use `"catalog:"` like the other `@types/*`
   entries. Until then it is pinned directly in `package.json`.
3. **No CI/turbo change required.** The existing studio `test`, `typecheck`,
   `lint`, `build` and (locally run) `e2e` scripts already cover the new code.
