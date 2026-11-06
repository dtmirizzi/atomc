# WP-3.7 `studio-3d` — R3F board/plate viewer with test-pad overlay

Read `_common.md`, PLAN §§1, 2, 4, 6, 8, 9 and `docs/architecture/contracts/{ir-schema,plugin-manifest}.md`. PR #12 just landed a live-data honesty pass: snapshots carry `dataMode` and telemetry notices and the UI must never imply facts it cannot source. This package extends that discipline to 3D geometry.

## Owned paths
- `apps/atomc-studio/src/viewer3d/**` (components, geometry derivation, tests' subjects)
- `apps/atomc-studio/src/model.ts` (additive only: geometry types if needed)
- `apps/atomc-studio/src/studio-app.tsx` (**minimal edits only**: one nav item + one view render line; put all logic under `viewer3d/`)
- `apps/atomc-studio/package.json` (add deps with `"catalog:"`)
- `apps/atomc-studio/test/viewer3d.test.tsx`, `apps/atomc-studio/e2e` (add your own spec file, do not edit existing specs)
- `apps/atomc-studio/README.md` (one Views bullet + a Run section note)
- `docs/plan/handoffs/WP-3.7.md`

Do not edit root workspace/lockfile/CI, daemon, client, harness packages or other apps. The lockfile importer update is orchestrator-owned; note it in the handoff.

## Deliverables
1. Geometry derivation (`viewer3d/geometry.ts`): pure functions turning IR data into renderable meshes — board outline (extruded plate from `/mechanical` or `/layout` outline data), switch cutouts/positions from `/keyboard` switch placements (19.05 mm pitch fixture data in `examples/atomc-pad/system_ir.json`), and test-pad markers from `/layout` test points. No geometry → an explicit `unavailable` state with a labeled notice, never a fake board.
2. R3F canvas (`viewer3d/BoardViewer.tsx`): `@react-three/fiber` + `three` from catalog; orbit controls via pointer events are optional; keyboard-accessible fallback controls or an accessible summary panel (mesh counts, bounds) must exist — the canvas alone must not be the only representation (axe must stay clean).
3. View wiring: a "3D viewer" nav entry rendering the viewer; demo mode renders fixture geometry clearly labeled as simulated (`dataMode` notice, same pattern as the agents view); daemon mode renders from the snapshot's IR-derived data or an honest unavailable notice when geometry is missing.
4. Determinism: geometry derivation is pure and unit-tested (bounds, cutout count/positions, test-pad mapping, empty-input behavior). WebGL rendering is not unit-asserted (jsdom has no WebGL); test the fallback/summary rendering and data flow. E2E (real Chromium, software WebGL) asserts the view renders and shows its data-source label — no pixel assertions.
5. Tests: unit tests for all derivation functions + component render with injected fixture data; one e2e spec file; axe scan on your view; existing studio tests stay green; coverage floor (`test:coverage:strict`) holds.
6. Handoff with exact commands, design decisions, deviations, root changes needed (lockfile importer).

## Definition of done
- `pnpm --filter @atomc/studio test`, `test:coverage:strict`, `typecheck`, `lint` all pass; `pnpm build` succeeds; your e2e spec passes locally.
- No invented geometry: every mesh traces to IR data or is labeled simulated; empty/absent inputs render honest notices.
- Conventional commits; push `wp/3.7-studio-3d`; do not merge.

## Stop and ask
If R3F/three current versions cannot install from the catalog, or WebGL-less e2e proves impossible in Chromium, stop and report instead of shipping a degraded fake.
