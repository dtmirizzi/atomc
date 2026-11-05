# atomc-keeb

48-key **4×12 ortholinear** QMK keyboard on an **STM32F411CEU6**
(blackpill-compatible pinout, QMK `BLACKPILL_STM32_F411`, `stm32-dfu`
bootloader). This is the flagship [atomc](../../PLAN.md) example: a real,
orderable end-to-end design driven by the unified system IR.

## What it is

* USB-C receptacle with 5.1 kΩ CC1/CC2 pull-downs and a **USBLC6-2SC6** ESD array
  on D+/D−.
* **AP2112K-3.3** LDO generating 3.3 V from VBUS, with input/output decoupling.
* **ABM8 25 MHz** HSE crystal (blackpill-compatible).
* BOOT0 pull-down + push button, NRST push button.
* SWD (SWDIO/SWCLK), UART (TX/RX), NRST and BOOT0 broken out to bottom-side test
  pads for the pogo-pin jig, plus a test pad on every row/column net.
* 4×12 **COL2ROW** matrix of Kailh MX hot-swap sockets, one **1N4148W** per switch
  (48 switches, 48 diodes).

## Pin map

### STM32F411CEU6 (U1, simplified seed pin numbering)

The `.ato` seed uses a reduced pin list; the QMK port names are authoritative.

| MCU pin | Port | Net | Function |
|--------:|------|-----|----------|
| 1  | —    | VBUS    | VBAT |
| 2  | —    | 3V3     | VDD |
| 3  | —    | BOOT0   | BOOT0 (10 kΩ pull-down + button) |
| 4  | —    | NRST    | Reset (button + test pad) |
| 5  | PA13 | SWDIO   | SWD data |
| 6  | PA14 | SWCLK   | SWD clock |
| 7  | PA9  | UART_TX | USART1 TX |
| 8  | PA10 | UART_RX | USART1 RX |
| 9  | A11  | USB_DM  | USB D− |
| 10 | A12  | USB_DP  | USB D+ |
| 11 | PH0  | HSE_IN  | 25 MHz crystal |
| 12 | PH1  | HSE_OUT | 25 MHz crystal |
| 13 | B12  | ROW0    | matrix row 0 |
| 14 | B13  | ROW1    | matrix row 1 |
| 15 | B14  | ROW2    | matrix row 2 |
| 16 | B15  | ROW3    | matrix row 3 |
| 17–28 | A0, A1, A2, A3, A5, A6, A7, B0, B1, B10, C14, C15 | COL0…COL11 | matrix columns |

Reserved by the MCU/board and **not** used by the matrix: `A11/A12` (USB),
`A13/A14` (SWD), `PH0/PH1` (HSE). USART1 is on `A9/A10`.

### Matrix (QMK `keyboard.json`)

| | COL0 A0 | COL1 A1 | COL2 A2 | COL3 A3 | COL4 A5 | COL5 A6 | COL6 A7 | COL7 B0 | COL8 B1 | COL9 B10 | COL10 C14 | COL11 C15 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **ROW0 B12** | K00 | K01 | K02 | K03 | K04 | K05 | K06 | K07 | K08 | K09 | K10 | K11 |
| **ROW1 B13** | K10 | K11 | K12 | K13 | K14 | K15 | K16 | K17 | K18 | K19 | K1A | K1B |
| **ROW2 B14** | K20 | K21 | K22 | K23 | K24 | K25 | K26 | K27 | K28 | K29 | K2A | K2B |
| **ROW3 B15** | K30 | K31 | K32 | K33 | K34 | K35 | K36 | K37 | K38 | K39 | K3A | K3B |

(`K<row><col>` labels match the `key:K<row>_<col>` ids in `system_ir.json`.)

## Build

```bash
source ~/.atomc/env.sh        # sources the toolchain PATH and QMK_HOME
ato build                     # atopile electrical/PCB build

# QMK firmware (default + renode keymaps)
cd qmk && ./build.sh all
```

`qmk/build.sh` symlinks `qmk/keyboards/atomc/*` into `$QMK_HOME/keyboards/atomc`
and runs `qmk compile -kb atomc/keeb -km {default,renode}`. `QMK_HOME` defaults to
`~/qmk_firmware`.

Recorded firmware sizes (`arm-none-eabi`, QMK master, 2026-11-04):

| Keymap  | `.bin` size |
|---------|------------:|
| default | 28 628 B |
| renode  | 32 012 B |

## Artifacts

* `system_ir.json` — hand-authored unified IR (48 keys, 48 switches/diodes),
  validated by `atomc_core_ir`.
* `atomc.config.ts` — budget gate (`bom.cost_under_budget`: 4500 ¢/board @ qty 5,
  excluding switches and keycaps).
* `elec/src/main.ato` — atopile 0.15 project (4×12 COL2ROW matrix).
* `qmk/` — QMK keyboard definition + default/renode keymaps.

## BOM notes

* `ato` part picking needs the atopile package registry (sign-in). The
  `elec/src/parts/` components here are hand-authored atomic seeds with generated
  minimal KiCad footprints/symbols so `ato build` is deterministic and offline;
  replace them with `ato create part` / `ato add` registry parts once signed in.
* Excluded from the budget gate: switches, keycaps.
