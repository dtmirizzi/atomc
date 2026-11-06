# atomc-pad (3×3 macropad)

::: info Current status
`examples/atomc-pad` is checked in with hand-written IR and QMK scaffolding. The atomc hardware plugins and full daemon build pipeline are not implemented yet.
:::

`atomc-pad` is the small development fixture: a 3×3 macropad used for source-level builds and planned atomc pipeline tests before scaling to the 48-key [atomc-keeb](/examples/atomc-keeb).

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

For a direct QMK build, set `QMK_HOME` to your local `qmk_firmware` checkout. Atomc does not yet run that command through a `fw.qmk_compile` plugin gate.
