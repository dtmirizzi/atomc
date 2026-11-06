# WP-4.2 `plugin-renode` — IR → Renode platform scripts and emulation gates

Read `_common.md`, PLAN §§1, 2, 4, 6, 8, 9 and `docs/architecture/contracts/{plugin-manifest,gate-result,ir-schema}.md`; the WP-2.2 plugin SDK; `examples/atomc-pad/{system_ir.json,qmk/}` and any committed `.repl/.resc` goldens. The daemon's warm renode kernel (`packages/daemon/python/src/atomcd/kernels/renode.py`) shows the honesty pattern. USB HID is **not** assumed emulated; Renode is a regression aid only.

## Owned paths
- `plugins/plugin-renode/**`
- `docs/plan/handoffs/WP-4.2.md`

Do not edit root workspace/lockfile/CI, daemon, other plugins or examples.

## Deliverables
1. Python plugin package `plugins/plugin-renode/python` (hatchling, src layout, `atomc.plugins` entry-point) with a validated manifest: `fw.renode_boot` gate, `fw.matrix_scan` gate, `renode.generate` tool, watches `/firmware` + `/simulation`, produces `/simulation`.
2. IR → scripts derivation (pure, unit-tested): `.repl` platform for STM32F411 (peripheral map needed by QMK ChibiOS: GPIO ports from IR matrix pins, USB/UART as available) and `.resc` script that loads the firmware artifact path from `/firmware` and runs with a bounded timeout. Byte-deterministic generation from the same IR input.
3. `fw.renode_boot` gate: run Renode headless (`renode --console`) on the generated scripts; missing renode binary → `SKIP` with evidence; boot success = no HardFault and expected UART banner within timeout → `PASS`; timeout/HardFault → `FAIL` with bounded log evidence. USB HID is explicitly **out of scope**: the gate never claims USB behavior.
4. `fw.matrix_scan` gate: **declared-not-implemented**: reports `SKIP` with evidence "GPIO matrix-injection model unproven; requires HIL board + pogo fixture" — the manifest documents it and the daemon reports it honestly. Do not fake a scan.
5. A recorded-HIL checklist document under your plugin dir (`docs/hil-checklist.md`) listing what must be verified on real hardware.
6. Tests: deterministic pytest suite (repl/resc generation goldens, gate SKIP/PASS/FAIL with a fake subprocess runner, manifest conformance). Ruff/mypy clean.
7. Handoff: exact commands, design decisions, deviations, root changes needed (should be none).

## Definition of done
- `uv run pytest plugins/plugin-renode/python` passes without renode installed.
- No fake PASS and no USB claims; every gate outcome traces to a subprocess exit or an explicit documented SKIP.
- Conventional commits; push `wp/4.2-plugin-renode`; do not merge.

## Stop and ask
If the IR firmware node lacks the artifact path or MCU identity your scripts need, stop and report the gap.
