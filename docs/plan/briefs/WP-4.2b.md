# WP-4.2b `plugin-qmk` — IR → QMK keyboard firmware generation and compile gate

Read `_common.md`, PLAN §§1, 2, 4, 6, 8, 9 and `docs/architecture/contracts/{plugin-manifest,gate-result,ir-schema}.md`; the WP-2.2 plugin SDK (Python) README/conformance tests; `examples/atomc-pad/{system_ir.json,qmk/}` (the fixture this plugin must reproduce from IR). The daemon's warm atopile kernel shows the honesty pattern: unavailable tools SKIP with evidence, never fake PASS.

## Owned paths
- `plugins/plugin-qmk/**` (pyproject with `atomc.plugins` entry-point, manifest, handlers, tests)
- `docs/plugins/` only via your own new doc file if the brief requires it (skip by default)
- `docs/plan/handoffs/WP-4.2b.md`

Do not edit root workspace/lockfile/CI, daemon, other plugins or examples. `plugins/*/python` is already a uv workspace member glob.

## Deliverables
1. Python plugin package `plugins/plugin-qmk/python` (hatchling, src layout, entry-point group `atomc.plugins`) with a validated manifest: `fw.qmk_compile` gate, `fw.matrix_pins_match_ir` gate, `qmk.compile`/`qmk.generate` tools, watches on `/keyboard` + `/firmware`, produces `/firmware`.
2. IR → QMK derivation (pure, unit-tested): `keyboard.json` (matrix rows/cols from IR `/keyboard` matrix, diode direction, layout geometry from switch placements, USB ids/vid/pid from IR), default keymap `keymap.c` (layers with a base layer derived from key positions), file layout under `keyboards/atomc/<name>/`. Must byte-match the committed `examples/atomc-pad/qmk/` fixture or document the exact intentional differences.
3. `fw.qmk_compile` gate: runs `qmk compile` via subprocess with `QMK_HOME` (keyboard symlinked into `keyboards/atomc/`); when qmk or `QMK_HOME` is missing → `SKIP` with evidence and a suggestion, never PASS; on success → `PASS` with duration + artifact sha256 written to `/firmware` via the plugin context (respect lock/produces scopes); on failure → `FAIL` with bounded compiler output in evidence.
4. `fw.matrix_pins_match_ir` gate: pure check that generated `keyboard.json` matrix pins match IR pins (unit-tested, always runs).
5. Tests: deterministic pytest suite (derivation golden tests against the example fixture, gate SKIP/PASS/FAIL paths with a fake subprocess runner, manifest conformance via the WP-2.2 SDK, no real qmk required). `uv run ruff check`, `ruff format --check`, `mypy` clean.
6. Handoff: exact commands, design decisions, deviations, root changes needed (should be none).

## Definition of done
- `uv run pytest plugins/plugin-qmk/python` passes without qmk installed (SKIP paths) and, if a qmk checkout exists locally, the compile gate is exercised once and recorded in the handoff.
- No fake PASS: every gate outcome traces to a real subprocess exit or a pure checked derivation.
- Conventional commits; push `wp/4.2b-plugin-qmk`; do not merge.

## Stop and ask
If the IR `/keyboard` node in the fixture lacks data your derivation needs (diode direction, usb ids), stop and report the exact gap rather than hardcoding values.
