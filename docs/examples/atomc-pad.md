# atomc-pad (3×3 macropad)

::: info Planned
`examples/atomc-pad` is seeded in Phase 1 (WP-1.6). This page describes the target.
:::

`atomc-pad` is the fast development fixture: a 3×3 macropad small enough to build and emulate in
seconds, used to validate the whole pipeline in Phase 4 before scaling to the 48-key
[atomc-keeb](/examples/atomc-keeb).

## Hardware

- **MCU:** STM32F411CEU6 (QMK ChibiOS-supported; Renode STM32F4 platform)
- **USB-C** receptacle with 5.1 kΩ CC pull-downs and a USBLC6-2SC6 ESD array
- **3.3 V LDO** (AP2112K-3.3 / XC6220 class)
- **Matrix:** 3×3 of MX hot-swap sockets with per-key 1N4148W diodes
- **Test pads:** SWD (SWDIO/SWCLK/NRST), UART TX/RX, BOOT0, VBUS, 3V3, GND, and every row/col net —
  routed to bottom-side pads the pogo jig can reach

## The IR

The hand-written `system_ir.json` exercises the whole schema:

- `/electrical` — 9 switches, 9 diodes, MCU, USB, LDO
- `/keyboard` — a 3×3 [matrix](/architecture/ir) with `row_pins`/`col_pins` and one `key` per position
- `/layout` — board outline, placements, and test pads
- `/firmware`, `/mechanical`, `/sourcing` — targets, jig params, and budget gates

## Budget

`atomc.config.ts` sets `bom.cost_under_budget` to **1500¢** per board at qty 5, excluding
switches and keycaps.

## Build it

```bash
cd examples/atomc-pad
ato build                          # atopile compile
qmk compile -kb atomc/pad -km default
```

The [QMK compile gate](/architecture/dag-gates) (`fw.qmk_compile`) verifies the firmware builds
against the user's `qmk_firmware` checkout via `QMK_HOME`.
