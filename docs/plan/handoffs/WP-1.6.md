# WP-1.6 `example-seed` — handoff

Status: **done** (both examples build and validate; one documented deviation on
part sourcing).

## What was built

Owned paths: `examples/atomc-pad/**`, `examples/atomc-keeb/**`.

### atomc-pad (3×3 macropad, STM32F411CEU6)
- `elec/src/main.ato` + `elec/src/parts/**` — atopile 0.15.9 project. 11
  hand-authored atomic parts (STM32F411CEU6, USB-C receptacle, AP2112K-3.3 LDO,
  USBLC6-2SC6 ESD, 25 MHz crystal, boot/reset push buttons, R/C 0402, 1N4148W,
  Kailh MX hot-swap socket, test point). Full circuit: USB-C + CC pull-downs, ESD,
  LDO, HSE, BOOT0/NRST, SWD/UART breakout, 3×3 COL2ROW matrix, 15 bottom-side
  pogo test pads, `assert` on VBUS/3V3. `ato build` **passes** (2.1 s).
- `qmk/` — `keyboard.json` (processor STM32F411, `stm32-dfu`, board
  `BLACKPILL_STM32_F411`, rows `B12/B13/B14`, cols `A0/A1/A2`, COL2ROW, x/y
  layout), `keymaps/default` and `keymaps/renode` (matrix debug + console),
  `build.sh`. Both keymaps compile (28 412 B / 31 756 B).
- `system_ir.json` — validated by `atomc_core_ir`; 9 keys, matrix 3×3, columns
  aligned to the QMK config; adds HSE (`comp:Y1`, nets `HSE_IN`/`HSE_OUT`).
- `atomc.config.ts`, `README.md` with pin map and build steps.

### atomc-keeb (4×12 ortholinear, STM32F411CEU6)
- `elec/src/main.ato` (404 lines generated from the IR) + same part library.
  48 switches + 48 diodes, COL2ROW, USB/LDO/HSE/debug, 27 pogo test pads.
  `ato build` **passes** (4.2 s).
- `qmk/` — 4×12 `keyboard.json` (rows `B12–B15`, cols `A0 A1 A2 A3 A5 A6 A7 B0 B1
  B10 C14 C15`), 2-layer default keymap + renode keymap. Both compile (28 628 B /
  32 012 B).
- `system_ir.json` — validated; 48 keys, matrix 4×12, budget gate 4500 ¢/board.
- `atomc.config.ts`, `README.md` with pin/matrix tables and build steps.

## How to verify (exact commands)

```bash
source ~/.atomc/env.sh
export QMK_HOME=~/qmk_firmware

# atopile (each example, from its directory)
cd examples/atomc-pad && ATO_NON_INTERACTIVE=1 ato build
cd ../atomc-keeb      && ATO_NON_INTERACTIVE=1 ato build

# QMK (default + renode keymaps)
cd examples/atomc-pad/qmk && ./build.sh all
cd ../../atomc-keeb/qmk   && ./build.sh all

# IR validation (from repo root)
uv run --with ./packages/core-ir/python --no-project python -c \
  "from atomc_core_ir import SystemIR; \
   SystemIR.load('examples/atomc-pad/system_ir.json'); \
   SystemIR.load('examples/atomc-keeb/system_ir.json'); print('ok')"
```

## Design decisions

- **Pin choices** avoid the MCU pins reserved by the blackpill/USB paths: USB
  `A11/A12`, SWD `A13/A14`, HSE `PH0/PH1`; USART1 on `A9/A10`. Rows start at
  `B12`; columns on `A0…C15` for the keeb. Recorded in each README.
- **COL2ROW** throughout: column → switch → diode anode → cathode → row.
- **System IR generated from the models** (one-off authoring helper) so it is
  guaranteed to validate; the JSON is committed as the deliverable.
- Keeb MCU pin numbering in `system_ir.json` and `.ato` are aligned (1–12 support
  circuit, 13–16 rows, 17–28 columns).
- `.ato/` and `build/` are git-ignored; the generated `layout/default.kicad_pcb`
  is committed as the default generated PCB.
- Hand-authored parts use generated minimal KiCad footprint/symbol files
  (correct internal `<part>:PACKAGE` names, one pad/pin per declared pin) so the
  build is deterministic and offline.

## Deviations from contract

- **Part sourcing (documented, not bent).** The brief asks for real parts via
  `ato create part` / `ato add`. atopile **0.15.8 CLI part picking and the
  package registry require sign-in** (`ato auth login`, app.atopile.io), which is
  unavailable here. All components are therefore hand-authored `is_atomic_part`
  seeds with `has_part_picked::by_supplier` so part picking is satisfied without
  the registry. Swap in real LCSC parts once authenticated.
- **Pad IR column pins** changed from the WP-1.1 fixture's `A8/A9/A10` to
  `A0/A1/A2` to avoid colliding with USART1 (`A9/A10`). The pad IR fixture is
  also extended with the 25 MHz HSE crystal (`comp:Y1`) so `.ato` and IR agree.
- `assert` is on the power interfaces (VBUS/3V3 voltage). Resistor/regulator
  value asserts would require generic `Resistor`/regulator parts (part picking),
  so CC/LDO value asserts are not present.

## Open issues

- `ato` footprint/symbol seeds are synthetic minimal geometry; the generated PCB
  is not manufacturable as-is (expected for Phase 1 — Phase 4 `plugin-atopile`
  extracts the real netlist and Phase 4 `plugin-cad-jig` builds mechanics).
- Real LCSC/EasyEDA parts for the STM32/USB-C/switch footprints are pending
  registry access.
- `biome check` on the two `atomc.config.ts` files was not run locally
  (no root `node_modules`); files are 2-space formatted to match repo style.

## Root changes needed

- None.
