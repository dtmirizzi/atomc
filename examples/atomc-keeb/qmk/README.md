# atomc-keeb QMK firmware

4x12 ortholinear keyboard (48 keys) on an STM32F411CEU6
(blackpill-compatible, `BLACKPILL_STM32_F411`, `stm32-dfu` bootloader).

## Keymaps

| Keymap | Purpose | Layers |
|--------|---------|--------|
| `default` | User-facing default keymap for the 48-key board. | Base + one function (lower) layer |
| `renode` | Emulation/debug keymap inherited from the Phase 1 fixture. It enables matrix/keyboard debug output for emulation runs. It is not a USB HID proof. | Base + one function (lower) layer |

WP-4.4 adds the UART-redirected debug keymap to the **pad only**, as requested.
The keeb renode keymap remains the existing emulation fixture.

## Build

```bash
source ~/.atomc/env.sh        # toolchain PATH and QMK_HOME
cd examples/atomc-keeb/qmk
./build.sh all                # default + renode
```

`build.sh` symlinks this repository's `keyboards/atomc/*` tree into
`$QMK_HOME/keyboards/atomc` and runs `qmk compile`. `QMK_HOME` defaults to
`~/qmk_firmware`.

## Emulation boundary

The `renode` keymap enables debug output for emulation. Renode does not emulate
USB HID for this target, so no simulated run proves USB enumeration or key
reports. Use the physical board and pogo jig for HIL; see
[`../hil/checklist.md`](../hil/checklist.md).

## Fixture validation

A dependency-free syntax/keycode sanity check lives at
[`../hil/check_keymaps.py`](../hil/check_keymaps.py). It checks balanced
delimiters and LAYOUT keycodes; it does not replace `qmk compile` and CI is not
expected to run it.

```bash
python3 examples/atomc-keeb/hil/check_keymaps.py
```

## Layout / matrix

Rows: `B12`, `B13`, `B14`, `B15`; columns: `A0 A1 A2 A3 A5 A6 A7 B0 B1 B10 C14
C15`; COL2ROW. Key labels `K00`..`K3B` match `system_ir.json`.
