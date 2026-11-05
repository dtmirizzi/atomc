# atomc-pad

3×3 ortholinear macropad on an **STM32F411CEU6** (blackpill-compatible pinout,
QMK `BLACKPILL_STM32_F411`, `stm32-dfu` bootloader). Part of the
[atomc](../../PLAN.md) examples: the fast development fixture for the electrical
→ firmware → enclosure → test-jig pipeline.

## What it is

* USB-C receptacle with 5.1 kΩ CC1/CC2 pull-downs and a **USBLC6-2SC6** ESD array
  on D+/D−.
* **AP2112K-3.3** LDO generating 3.3 V from VBUS, with input/output decoupling.
* **ABM8 25 MHz** HSE crystal (blackpill-compatible).
* BOOT0 pull-down + push button, NRST push button.
* SWD (SWDIO/SWCLK), UART (TX/RX), NRST and BOOT0 broken out to bottom-side test
  pads for the pogo-pin jig.
* 3×3 **COL2ROW** matrix of Kailh MX hot-swap sockets, one **1N4148W** per switch.

## Pin map

### STM32F411CEU6 (U1, simplified seed pin numbering)

The `.ato` seed uses a reduced pin list; the QMK port names are authoritative.

| MCU pin | Port | Net | Function |
|--------:|------|-----|----------|
| 1  | —    | 3V3     | VDD |
| 2  | —    | GND     | VSS |
| 3  | —    | BOOT0   | BOOT0 (10 kΩ pull-down + button) |
| 4  | —    | NRST    | Reset (button + test pad) |
| 5  | PA13 | SWDIO   | SWD data |
| 6  | PA14 | SWCLK   | SWD clock |
| 7  | PA9  | UART_TX | USART1 TX |
| 8  | PA10 | UART_RX | USART1 RX |
| 9  | B12  | ROW0    | matrix row 0 |
| 10 | B13  | ROW1    | matrix row 1 |
| 11 | B14  | ROW2    | matrix row 2 |
| 12 | A0   | COL0    | matrix column 0 |
| 13 | A1   | COL1    | matrix column 1 |
| 14 | A2   | COL2    | matrix column 2 |
| 15 | A12  | USB_DP  | USB D+ |
| 16 | A11  | USB_DM  | USB D− |
| 17 | PH0  | HSE_IN  | 25 MHz crystal |
| 18 | PH1  | HSE_OUT | 25 MHz crystal |

Reserved by the MCU/board and **not** used by the matrix: `A11/A12` (USB),
`A13/A14` (SWD), `PH0/PH1` (HSE). USART1 is on `A9/A10`.

### Matrix (QMK `keyboard.json`)

| | COL0 (A0) | COL1 (A1) | COL2 (A2) |
|---|---|---|---|
| **ROW0 (B12)** | K00 | K01 | K02 |
| **ROW1 (B13)** | K10 | K11 | K12 |
| **ROW2 (B14)** | K20 | K21 | K22 |

## Build

```bash
source ~/.atomc/env.sh        # sources the toolchain PATH and QMK_HOME
ato build                     # atopile electrical/PCB build

# QMK firmware (default + renode keymaps)
cd qmk && ./build.sh all
```

`qmk/build.sh` symlinks `qmk/keyboards/atomc/*` into `$QMK_HOME/keyboards/atomc`
and runs `qmk compile -kb atomc/pad -km {default,renode}`. `QMK_HOME` defaults to
`~/qmk_firmware`.

Recorded firmware sizes (`arm-none-eabi`, QMK master, 2026-11-04):

| Keymap  | `.bin` size |
|---------|------------:|
| default | 28 412 B |
| renode  | 31 756 B |

## Artifacts

* `system_ir.json` — hand-authored unified IR, validated by `atomc_core_ir`.
* `atomc.config.ts` — budget gate (`bom.cost_under_budget`: 1500 ¢/board @ qty 5,
  excluding switches and keycaps).
* `elec/src/main.ato` — atopile 0.15 project.
* `qmk/` — QMK keyboard definition + default/renode keymaps.

## BOM notes

* `ato` part picking needs the atopile package registry (sign-in). The
  `elec/src/parts/` components here are hand-authored atomic seeds with generated
  minimal KiCad footprints/symbols so `ato build` is deterministic and offline;
  replace them with `ato create part` / `ato add` registry parts once signed in.
* Excluded from the budget gate: switches, keycaps.
