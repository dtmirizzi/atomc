# WP-4.4 — example-firmware handoff

## What was built

* **Keymaps**
  * `examples/atomc-pad/qmk/keyboards/atomc/pad/keymaps/default/keymap.c` remains
    the byte-for-byte plugin-qmk derivation fixture (single base layer, digits
    1–9); it was not edited.
  * Added `keymaps/utility/keymap.c` for the pad: base digits plus a media /
    utility layer reached by holding K22 (`LT(_UTIL, KC_9)`). This supplies the
    requested pad layer set without breaking the derivation goldens.
  * Updated the pad `keymaps/renode/keymap.c` to an explicitly labelled
    emulation/debug build that redirects QMK's `print`/debug sink to USART1
    (`uart_init(115200)` + `print_set_sendchar`) and enables matrix/keyboard
    debug output. It does not claim USB HID under emulation.
  * Added pad `keymaps/renode/rules.mk` settings `CONSOLE_ENABLE`,
    `DEBUG_MATRIX_SCAN_RATE_ENABLE` and `UART_DRIVER_REQUIRED`.
  * Added pad `keymaps/renode/mcuconf.h`: `#include_next <mcuconf.h>` then
    `#undef/#define STM32_SERIAL_USE_USART1 TRUE`. The Blackpill board config
    leaves USART1 disabled, which otherwise fails with “SERIAL driver activated
    but no USART/UART peripheral assigned”.
  * Keeb default keymap is base + one function/lower layer; the existing keeb
    renode keymap is retained as the emulation debug fixture.
* **HIL checklists**
  * `examples/atomc-pad/hil/checklist.md` — bench inspection, DFU entry/recovery,
    USB enumeration, all 9 matrix positions, layer tap test. Every hardware step
    explicitly requires the physical board + pogo jig.
  * `examples/atomc-keeb/hil/checklist.md` — same structure for all 48 positions.
  * Both state that simulation is not a HIL pass and does not prove USB/HID,
    matrix scan correctness or bootloader recovery.
* **Fixture syntax check**
  * `examples/atomc-pad/hil/check_keymaps.py` and the matching keeb script:
    dependency-free Python 3 checker for balanced delimiters and LAYOUT keycode /
    local macro whitelist. It skips gracefully if no keymaps are present and is
    not wired into CI.
* **Documentation**
  * Added `examples/atomc-pad/qmk/README.md` and
    `examples/atomc-keeb/qmk/README.md` covering keymaps, build commands, the
    renode/UART boundary and fixture validation.

## How to verify (exact commands)

```bash
cd /Users/dtmirizzi/.herdr/worktrees/atomc/wp-4.4-example-firmware

# 1. Plugin derivation goldens (must pass untouched)
uv run pytest plugins/plugin-qmk/python -q

# 2. Fixture keymap syntax/keycode checks (no QMK required)
python3 examples/atomc-pad/hil/check_keymaps.py
python3 examples/atomc-keeb/hil/check_keymaps.py

# 3. Lint/format the committed Python checkers
uv run ruff check examples/atomc-pad/hil/check_keymaps.py \
  examples/atomc-keeb/hil/check_keymaps.py
uv run ruff format --check examples/atomc-pad/hil/check_keymaps.py \
  examples/atomc-keeb/hil/check_keymaps.py

# 4. Compile with a real QMK tree (local run recorded below)
source ~/.atomc/env.sh
cd examples/atomc-pad/qmk && ./build.sh all
qmk compile -kb atomc/pad -km utility
cd ../../atomc-keeb/qmk && ./build.sh all
```

## Compile results (local QMK_HOME, QMK 1.2.0)

| Keyboard | Keymap | Result | `.bin` size |
|----------|--------|--------|-------------|
| atomc/pad | default | PASS | 28 412 B |
| atomc/pad | utility | PASS | 28 436 B |
| atomc/pad | renode | PASS | 33 412 B |
| atomc/keeb | default | PASS | 28 628 B |
| atomc/keeb | renode | PASS | 32 012 B |

`uv run pytest plugins/plugin-qmk/python -q` → **39 passed**.
Both `check_keymaps.py` scripts → **PASS** for all five keymaps.
Ruff check/format on both checkers → clean.

## Design decisions

* **Layer set in `utility`, not `default`.** The plugin-qmk derivation tests
  compare `keymaps/default/keymap.c` byte-for-byte with the generated keymap.
  Keeping `default` single-layer preserves that golden; the pad base + media /
  utility layer set lives in the sibling `utility` keymap instead. The README
  documents this explicitly.
* **Keymap-local `mcuconf.h`.** The board default disables USART1. The renode
  keymap needs the QMK UART driver, so a keymap-local `mcuconf.h` enables it
  without touching the derived `keyboard.json` or board files.
* **Emulation boundary.** Pad renode output goes to USART1 (A9/A10); keeb renode
  uses QMK's console/debug output. Neither is presented as USB HID proof.
* **HIL is physical only.** Checklist wording requires the assembled board and
  pogo jig for every key, USB and bootloader item.

## Deviations from contract

None. The `default` keymap and derived `keyboard.json` files are untouched; the
pad layer set is an additional keymap rather than a change to the derived
fixture. The brief did not require editing the derived default in place.

## Open issues

* The utility keymap is not enumerated by the existing `build.sh`; the README
  documents the manual `qmk compile -kb atomc/pad -km utility` command. Changing
  `build.sh` was outside this work package's owned paths.
* The committed syntax checker validates structure and keycode shapes only; it
  is not a substitute for `qmk compile`.

## Root changes needed

None.
