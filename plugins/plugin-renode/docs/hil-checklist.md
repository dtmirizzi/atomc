# Renode ↔ hardware boundary: recorded-HIL checklist

Renode is a **regression aid**, not proof of end-user behaviour. The `plugin-renode` gates only
claim what the STM32F4 model actually demonstrates: CPU boot, memory loads, and whatever peripheral
output the model happens to produce. The following must be verified on a real board (with the pogo
jig once it exists) before any release. Record each run under `tests/hil/<date>/` with the firmware
sha256, board serial, and raw capture.

## Scope of the emulation gates

| Gate | Renode claim | Not claimed |
| --- | --- | --- |
| `gate:fw.renode_boot` | no HardFault and a configured banner from the model | real clock tree, real USB, real matrix |
| `gate:fw.matrix_scan` | **nothing** — always `SKIP` | any key scan at all |

`gate:fw.matrix_scan` is intentionally declared-not-implemented because the QMK matrix path depends
on GPIO pulls, diode direction, debounce timing and USB HID reporting. None of that is proven in the
generic STM32F4 model, so a "scan" would be theatre.

## Equipment

- Assembled `atomc-pad` / `atomc-keeb` board, populated and reflowed.
- Pogo-pin jig (WP-4.3) seated on the bottom test pads, **or** hand probes for a one-off bring-up.
- ST-Link / CMSIS-DAP probe wired to SWDIO, SWCLK, NRST, GND (3V3 reference as needed).
- Host with `openocd` (or `pyocd`) and a USB-A/C port for HID capture.
- Optional: logic analyser on the matrix lines; USB protocol analyser.

## Bring-up (once per board revision)

1. **Power rails** — measure 5 V (VBUS), 3.3 V (LDO out) and GND at the test pads. Record values.
2. **SWD attach** — `openocd -f interface/stlink.cfg -f target/stm32f4x.cfg`; confirm the MCU id.
3. **Flash** — `openocd ... -c "program build/atomc-pad.elf verify reset exit"`. Confirm the same
   sha256 that is recorded in `/firmware/targets/*/artifacts`.
4. **Boot console** — attach the UART test pad (TX/RX) at the firmware baud; confirm the firmware
   prints the boot banner that `gate:fw.renode_boot` looks for, or update the banner markers in
   `/ext/renode/boot_markers` so the emulated gate matches the real string.
5. **No HardFault watchdog** — run for 60 s; confirm the firmware does not reset-loop.

## USB HID (required release blocker)

6. **Enumeration** — plug into a host; confirm VID/PID from `/keyboard/usb` appear
   (`lsusb`/`system_profiler SPUSBDataType`). This cannot be proven in Renode.
7. **Bootloader entry** — hold BOOT0 (or trigger via keymap) and confirm DFU enumeration.
8. **Bootloader recovery** — force a bad image, re-enter DFU, reflash, confirm recovery.
9. **All-keys report** — for **every** `key:K<row>_<col>` in `/keyboard/keys`, short the switch
   position (or press the physical key) and confirm the expected keycode reaches the host. Use the
   `keymaps/renode` debug build on the bench, but capture HID on the host — not `debug_matrix`.
10. **Diode direction** — verify a single key press produces exactly one report (COL2ROW as declared)
    and that no ghosting appears when three keys in an L form are held.

## Matrix electrical checks

11. **Pull-ups / idle level** — with no keys pressed, confirm each column reads pulled high and each
   row is driven low in turn.
12. **Debounce** — press and release a key at normal speed; confirm exactly one press and one
    release event (no bounce reports).
13. **Scan timing** — with the `renode` keymap (`DEBUG_MATRIX_SCAN_RATE_ENABLE = api`), record the
    reported scan rate and confirm it meets the target for the matrix size.

## Sign-off

- [ ] Rails measured and recorded
- [ ] SWD attach + flash of the sha256 recorded in IR
- [ ] Real boot banner captured
- [ ] USB enumeration (VID/PID) confirmed
- [ ] Bootloader entry + recovery confirmed
- [ ] All keys report the expected keycode (count = `len(keyboard.keys)`)
- [ ] Diode direction / no ghosting confirmed
- [ ] Debounce and scan-rate recorded

Only after all boxes are checked may the release notes claim keyboard functionality. Renode results
are recorded as regression evidence, never as HIL evidence.
