# WP-1.6 `example-seed` — atomc-pad + atomc-keeb (atopile + QMK)

Read `_common.md` first, then PLAN §0 D8/D9, §8 WP-1.6, and `docs/architecture/contracts/ir-schema.md`
(§4.3 keyboard node). Environment notes: `docs/plan/ENVIRONMENT.md` (from WP-0.1). Source
`~/.atomc/env.sh` first. `QMK_HOME=~/qmk_firmware`.

## Owned paths
`examples/atomc-pad/**`, `examples/atomc-keeb/**`.

## Deliverables (do atomc-pad completely first, then atomc-keeb)
1. atopile 0.15.9 projects (`ato.yaml`, `elec/src/*.ato`, layout dir as ato creates it). Use `ato create`
   / `ato add` to pull real parts from the atopile package registry where available (STM32F411, USB-C
   receptacle, USBLC6-2SC6, LDO, 1N4148W, Kailh MX hot-swap socket). If a package doesn't exist, write
   the component with `ato create part` (LCSC-backed). Circuit: STM32F411CEU6 + 25 MHz HSE (blackpill
   compatible), decoupling per datasheet, USB-C (5.1 kΩ CC1/CC2 to GND), USBLC6 ESD on D+/D-,
   3.3 V LDO from VBUS, BOOT0 pull-down + button, NRST cap + button, SWD header pads, UART pads,
   key matrix with one diode per switch (COL2ROW), bottom-side test points (via `ato` test-point
   parts or 1 mm pads) for VBUS, 3V3, GND, SWDIO, SWCLK, NRST, BOOT0, TX, RX and every row/col net.
   Use atopile `assert` for regulator output voltage and CC resistor values. `ato build` must pass
   (layout/routing not required; if ato build insists on a layout, accept its default generated PCB).
   - atomc-pad: 3×3 matrix. atomc-keeb: 4×12 ortholinear (rows 4, cols 12).
   - Pick MCU pins that QMK's STM32F411 blackpill conventions allow (avoid A11/A12 = USB, A13/A14 = SWD,
     the HSE pins). Record pin choices in each example's README.
2. `qmk/keyboards/atomc/<pad|keeb>/`: `keyboard.json` (processor STM32F411, bootloader stm32-dfu,
   board BLACKPILL_STM32_F411, matrix_pins, diode_direction, usb vid/pid/device_version, layout with
   x/y per key matching the IR), `keymaps/default/keymap.c`, and `keymaps/renode/` (same + `CONSOLE_ENABLE`,
   debug matrix on, for emulation in Phase 4) + `rules.mk`/`keymap.json` as needed. Make a script
   `qmk/build.sh` that symlinks `keyboards/atomc` into `$QMK_HOME/keyboards/atomc` and runs
   `qmk compile -kb atomc/<name> -km default` (and `-km renode`). Both must compile; record binary sizes.
3. `system_ir.json` per example, hand-written, consistent with the .ato and keyboard.json (same designators,
   nets, pins, matrix). Validate it with WP-1.1's models: when `origin/wp/1.1-core-ir-py` has the package,
   run `uv run --with ./<path-to-a-checkout-of-that-branch>/packages/core-ir/python python -c "from atomc_core_ir import SystemIR; SystemIR.load('system_ir.json')"`
   (use `git worktree add /tmp/core-ir origin/wp/1.1-core-ir-py` to get the code). If it doesn't validate
   and you believe the IR is correct per contract, report the mismatch in your handoff — don't bend the IR.
4. `atomc.config.ts` stub per example (plain object export: project name, budget gates: pad 1500 / keeb
   4500 USD cents per board @ qty 5, excluding switches/keycaps; enabled plugins list).
5. README per example: what it is, pin map table, how to build (`ato build`, `qmk/build.sh`), BOM notes.

## Definition of done
`cd examples/atomc-pad && ato build` ✓, `examples/atomc-pad/qmk/build.sh` ✓ (default + renode keymaps),
same for atomc-keeb, both `system_ir.json` validate (or mismatches documented), handoff + push.
