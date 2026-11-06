# WP-4.1 `plugin-atopile` — atopile compilation, PCB import and ERC gates

Read `_common.md`, PLAN §§1, 2, 4, 6, 8, 9 and `docs/architecture/contracts/{plugin-manifest,gate-result,ir-schema}.md`; the WP-2.2 plugin SDK; `examples/atomc-pad/{system_ir.json,elec/}`; the daemon's atopile/kiutils kernels (`packages/daemon/python/src/atomcd/kernels/{atopile,kiutils}.py`) — atopile 0.15 has no supported build API, so compilation goes through the `ato` CLI subprocess; kiutils parses `.kicad_pcb`.

## Owned paths
- `plugins/plugin-atopile/**`
- `docs/plan/handoffs/WP-4.1.md`

Do not edit root workspace/lockfile/CI, daemon, other plugins or examples.

## Deliverables
1. Python plugin package `plugins/plugin-atopile/python` (hatchling, src layout, `atomc.plugins` entry-point) with a validated manifest: gates `erc.no_unconnected`, `erc.assertions`, `layout.testpads.min_count`, `layout.testpads.nets_covered`; tools `atopile.compile`, `atopile.import_pcb`; watches `/electrical` + `/layout`, produces `/electrical` + `/layout`.
2. `atopile.compile` tool: run `ato build` via subprocess in the project's elec dir; missing `ato` CLI → structured unavailable with evidence; success → PASS evidence + extracted components/nets written to `/electrical` through the plugin context (respect scopes, bounded output); failure → FAIL with bounded compiler output. Never call atopile internals.
3. `atopile.import_pcb` tool: parse `.kicad_pcb` with kiutils (optional import; unavailable without it) into outline + pad coordinates + net names, writing test-point data to `/layout`. Deterministic parse tests use a committed minimal `.kicad_pcb` fixture under your plugin's tests.
4. ERC gates are **pure checks over IR `/electrical` data**: `erc.no_unconnected` (no net with a single pin), `erc.assertions` (atopile assertion results recorded in IR pass). Test-pad gates are pure checks over `/layout` test-point data: min count threshold, matrix-net coverage. All gates always run; no subprocess needed.
5. Tests: deterministic pytest suite (subprocess fake runner for compile PASS/FAIL/unavailable, kiutils parse fixture goldens, all four gates PASS/FAIL on mutated fixtures, manifest conformance). Ruff/mypy clean.
6. Handoff: exact commands, design decisions, deviations, root changes needed (should be none).

## Definition of done
- `uv run pytest plugins/plugin-atopile/python` passes without atopile/kiutils installed; if locally importable, exercise the real paths once and record results in the handoff.
- No fake PASS: compile outcomes trace to subprocess exits; gates trace to IR data.
- Conventional commits; push `wp/4.1-plugin-atopile`; do not merge.

## Stop and ask
If `examples/atomc-pad/elec/` fixtures or the IR `/electrical` node lack the net/pin/assertion structure the gates need, stop and report the exact gap.
