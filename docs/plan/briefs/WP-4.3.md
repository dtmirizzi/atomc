# WP-4.3 `plugin-cad-jig` — build123d plate/case/jig generation with collision gates

Read `_common.md`, PLAN §§1, 2, 4, 6, 8, 9 and `docs/architecture/contracts/{plugin-manifest,gate-result,ir-schema}.md`; the WP-2.2 plugin SDK; `examples/atomc-pad/{system_ir.json,layout/}`; the daemon's `ocp`/`ocp_engine` kernels for the honesty pattern. build123d/CadQuery may not be installed — the plugin must stay deterministic and green without it.

## Owned paths
- `plugins/plugin-cad-jig/**`
- `docs/plan/handoffs/WP-4.3.md`

Do not edit root workspace/lockfile/CI, daemon, other plugins or examples.

## Deliverables
1. Python plugin package `plugins/plugin-cad-jig/python` (hatchling, src layout, `atomc.plugins` entry-point) with a validated manifest: gates `mech.plate_switch_cutouts_14mm`, `mech.case_usb_cutout_aligned`, `mech.pogo_spacing_ge_2p54`, `mech.jig_no_collision`, `mech.enclosure_clearance`; tools `cad.generate`; watches `/mechanical` + `/layout`, produces `/mechanical`.
2. Parametric model derivation (pure, unit-tested, no CAD import): switch-plate model data (14 mm cutouts at 19.05 mm pitch from IR switch placements, plate bounds from outline), case model data (tray-mount walls, USB-C cutout position from the IR connector placement), pogo jig model data (P75 receptacle positions from `/layout` test points, alignment pins on mounting holes). Geometry math (cutout centers, wall thickness, clearances) is plain arithmetic — test it exactly.
3. Gate implementations are **pure checks over the derived model data and IR**: cutout diameter/pitch correctness, USB cutout alignment delta, pogo center-to-center spacing ≥ 2.54 mm, jig/PCB collision check on the 2D footprint projection, enclosure clearance. All gates always run — no CAD dependency required for the gates.
4. `cad.generate` tool: builds solids via build123d **only when importable**; otherwise returns a structured unavailable result with evidence (never a fake STEP). Exports `.step/.stl` into the project build dir and records artifact refs into `/mechanical` through the plugin context (respect scopes). Skip PNG renders for now; note them as a follow-up.
5. Tests: deterministic pytest suite (model-data goldens from the atomc-pad fixture, all five gates PASS/FAIL paths on mutated fixtures, tool SKIP path without build123d, manifest conformance). Ruff/mypy clean.
6. Handoff: exact commands, design decisions, deviations, root changes needed (should be none).

## Definition of done
- `uv run pytest plugins/plugin-cad-jig/python` passes without build123d installed; if build123d is importable locally, exercise the tool once and record results in the handoff.
- Gates are pure and honest: no CAD import needed to verify a design; generated artifacts are never claimed when the tool is unavailable.
- Conventional commits; push `wp/4.3-plugin-cad-jig`; do not merge.

## Stop and ask
If the IR `/layout` or `/mechanical` nodes lack test-point or outline data the gates need, stop and report the exact fields.
