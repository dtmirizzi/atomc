# atomc-pad QMK firmware

3x3 ortholinear macropad on an STM32F411CEU6 (blackpill-compatible,
`BLACKPILL_STM32_F411`, `stm32-dfu` bootloader).

## Keymaps

| Keymap | Purpose | Layers |
|--------|---------|--------|
| `default` | Byte-for-byte derived fixture used by the `plugin-qmk` golden tests. Do not edit unless the derivation contract changes. | Single base layer, digits 1-9 |
| `utility` | User-facing layer set for the pad: base digits plus a media/utility layer reached by holding K22. | Base + utility |
| `renode` | **Emulation/debug build only.** Same base key assignments as `default`, with QMK's print/debug sink redirected to USART1 (A9/A10) so a Renode capture can correlate matrix scans. It does **not** claim USB HID works under emulation. | Single base layer |

The `default` keymap remains single-layer because the plugin-qmk derivation
goldens compare it byte-for-byte. The requested base + media/utilities layer set
therefore lives in the `utility` keymap rather than in `default`.

## Build

```bash
source ~/.atomc/env.sh        # toolchain PATH and QMK_HOME
cd examples/atomc-pad/qmk
./build.sh all                # default + renode
# Utility layer set (build.sh does not enumerate it):
qmk compile -kb atomc/pad -km utility
```

`build.sh` symlinks this repository's `keyboards/atomc/*` tree into
`$QMK_HOME/keyboards/atomc` and runs `qmk compile`. `QMK_HOME` defaults to
`~/qmk_firmware`.

## Renode/UART debug keymap

`keymaps/renode/keymap.c` calls `print_set_sendchar(uart_sendchar)` after
`uart_init(115200)`, so QMK's `debug_matrix`/`debug_keyboard` output is sent over
USART1. `keymaps/renode/rules.mk` sets `UART_DRIVER_REQUIRED = yes` to pull in
`uart_serial.c`. The keymap-local `keymaps/renode/mcuconf.h` overrides the
Blackpill board default to enable `STM32_SERIAL_USE_USART1`; without it the
ChibiOS serial driver fails at compile time because no UART peripheral is
assigned.

This is an emulation/debug aid only. It does not prove USB HID enumeration or
matrix correctness; those require the physical board and pogo jig. See
[`../hil/checklist.md`](../hil/checklist.md).

## Fixture validation

A dependency-free syntax/keycode sanity check lives at
[`../hil/check_keymaps.py`](../hil/check_keymaps.py). It checks balanced
delimiters and LAYOUT keycodes; it does not replace `qmk compile` and CI is not
expected to run it.

```bash
python3 examples/atomc-pad/hil/check_keymaps.py
```

## Layout / matrix

Rows: `B12`, `B13`, `B14`; columns: `A0`, `A1`, `A2`; COL2ROW. Key labels
`K00`..`K22` match `system_ir.json`.
