# atomc-keeb hardware-in-the-loop (HIL) checklist

> **Physical hardware only.** Every item below requires the assembled atomc-keeb
> board plus the pogo-pin jig. Simulation (Renode) is a regression aid and does
> **not** prove USB HID, matrix scan correctness, or bootloader recovery. Do not
> mark a simulated run as a HIL pass.

## Prerequisites

- [ ] Assembled `atomc-keeb` PCB (STM32F411CEU6, 4x12 COL2ROW matrix).
- [ ] Pogo-pin jig for the 27 bottom-side test pads (rows `B12-B15`, cols
      `A0 A1 A2 A3 A5 A6 A7 B0 B1 B10 C14 C15`, UART `A9/A10`, SWD, NRST, BOOT0).
- [ ] USB-C cable and a host with `lsusb` (Linux/macOS) and `hid_listen` or
      `qmk console`.
- [ ] DFU tool (`dfu-util`) or SWD tool (`openocd`) for flashing/recovery.
- [ ] Multimeter for continuity and rail checks.

## 1. Bench inspection (physical board)

- [ ] Verify no shorts between 3V3 and GND before applying power.
- [ ] Verify 5.1 kΩ CC1/CC2 pull-downs are populated.
- [ ] Verify 48 switches and 48 1N4148W diodes, COL2ROW orientation.
- [ ] Verify BOOT0 pull-down and NRST pull-up/button.
- [ ] Verify UART `A9/A10`, SWD `A13/A14`, and matrix test pads are reachable by
      the pogo jig.

## 2. Bootloader entry (physical board)

- [ ] Hold `BOOT0`, press and release `NRST`, then release `BOOT0`.
- [ ] Confirm the host sees the STM32 DFU device (`dfu-util -l`; VID:PID
      `0483:df11`).
- [ ] Flash the default keymap `.bin` with `dfu-util -a 0 -s 0x08000000:leave -D <bin>`.
- [ ] Confirm the board leaves DFU and starts running.

## 3. USB enumeration (physical board)

- [ ] Connect the board over USB-C.
- [ ] Confirm host enumeration of VID:PID `0xFEED:0x0002`.
- [ ] Confirm a HID keyboard interface is present (`lsusb -v` or OS keyboard
      settings).
- [ ] Open `hid_listen`/`qmk console` and confirm no enumeration errors.
- [ ] If the board does not enumerate, re-check the USB-C CC resistors and the
      USBLC6 ESD array before reflashing.

## 4. Every key position (pogo jig or physical press)

For each row/column, short the row/column test pads with the pogo jig **or**
press the physical switch, then confirm the expected HID keycode on the host.
Items marked **[pogo]** explicitly require the pogo jig; a physical press is an
acceptable substitute only when the switch is populated and the jig is unavailable.

| Key | Row | Col | Base keycode | Lower-layer keycode | Test |
|-----|----:|----:|--------------|---------------------|------|
| K00 | 0 | 0 | `KC_1` | `KC_F1` | [ ] **[pogo]** |
| K01 | 0 | 1 | `KC_2` | `KC_F2` | [ ] **[pogo]** |
| K02 | 0 | 2 | `KC_3` | `KC_F3` | [ ] **[pogo]** |
| K03 | 0 | 3 | `KC_4` | `KC_F4` | [ ] **[pogo]** |
| K04 | 0 | 4 | `KC_5` | `KC_F5` | [ ] **[pogo]** |
| K05 | 0 | 5 | `KC_6` | `KC_F6` | [ ] **[pogo]** |
| K06 | 0 | 6 | `KC_7` | `KC_F7` | [ ] **[pogo]** |
| K07 | 0 | 7 | `KC_8` | `KC_F8` | [ ] **[pogo]** |
| K08 | 0 | 8 | `KC_9` | `KC_F9` | [ ] **[pogo]** |
| K09 | 0 | 9 | `KC_0` | `KC_F10` | [ ] **[pogo]** |
| K010 | 0 | 10 | `KC_MINS` | `KC_F11` | [ ] **[pogo]** |
| K011 | 0 | 11 | `KC_EQL` | `KC_F12` | [ ] **[pogo]** |
| K10 | 1 | 0 | `KC_Q` | `_______` | [ ] **[pogo]** |
| K11 | 1 | 1 | `KC_W` | `_______` | [ ] **[pogo]** |
| K12 | 1 | 2 | `KC_E` | `_______` | [ ] **[pogo]** |
| K13 | 1 | 3 | `KC_R` | `_______` | [ ] **[pogo]** |
| K14 | 1 | 4 | `KC_T` | `_______` | [ ] **[pogo]** |
| K15 | 1 | 5 | `KC_Y` | `_______` | [ ] **[pogo]** |
| K16 | 1 | 6 | `KC_U` | `_______` | [ ] **[pogo]** |
| K17 | 1 | 7 | `KC_I` | `KC_PSCR` | [ ] **[pogo]** |
| K18 | 1 | 8 | `KC_O` | `KC_SCRL` | [ ] **[pogo]** |
| K19 | 1 | 9 | `KC_P` | `KC_PAUS` | [ ] **[pogo]** |
| K110 | 1 | 10 | `KC_LBRC` | `_______` | [ ] **[pogo]** |
| K111 | 1 | 11 | `KC_RBRC` | `_______` | [ ] **[pogo]** |
| K20 | 2 | 0 | `KC_A` | `_______` | [ ] **[pogo]** |
| K21 | 2 | 1 | `KC_S` | `_______` | [ ] **[pogo]** |
| K22 | 2 | 2 | `KC_D` | `_______` | [ ] **[pogo]** |
| K23 | 2 | 3 | `KC_F` | `_______` | [ ] **[pogo]** |
| K24 | 2 | 4 | `KC_G` | `_______` | [ ] **[pogo]** |
| K25 | 2 | 5 | `KC_H` | `_______` | [ ] **[pogo]** |
| K26 | 2 | 6 | `KC_J` | `KC_LEFT` | [ ] **[pogo]** |
| K27 | 2 | 7 | `KC_K` | `KC_DOWN` | [ ] **[pogo]** |
| K28 | 2 | 8 | `KC_L` | `KC_UP` | [ ] **[pogo]** |
| K29 | 2 | 9 | `KC_SCLN` | `KC_RGHT` | [ ] **[pogo]** |
| K210 | 2 | 10 | `KC_QUOT` | `_______` | [ ] **[pogo]** |
| K211 | 2 | 11 | `KC_ENT` | `_______` | [ ] **[pogo]** |
| K30 | 3 | 0 | `KC_Z` | `_______` | [ ] **[pogo]** |
| K31 | 3 | 1 | `KC_X` | `_______` | [ ] **[pogo]** |
| K32 | 3 | 2 | `KC_C` | `_______` | [ ] **[pogo]** |
| K33 | 3 | 3 | `KC_V` | `_______` | [ ] **[pogo]** |
| K34 | 3 | 4 | `KC_B` | `_______` | [ ] **[pogo]** |
| K35 | 3 | 5 | `KC_N` | `_______` | [ ] **[pogo]** |
| K36 | 3 | 6 | `KC_M` | `_______` | [ ] **[pogo]** |
| K37 | 3 | 7 | `KC_COMM` | `_______` | [ ] **[pogo]** |
| K38 | 3 | 8 | `KC_DOT` | `_______` | [ ] **[pogo]** |
| K39 | 3 | 9 | `KC_SLSH` | `KC_HOME` | [ ] **[pogo]** |
| K310 | 3 | 10 | `KC_UP` | `KC_PGUP` | [ ] **[pogo]** |
| K311 | 3 | 11 | layer key (`MO(_LOWER)`) | `_______` | [ ] **[pogo]** |

### Layer test

- [ ] Hold K311 and press K00-K39; confirm the lower-layer keycodes in the table.
- [ ] Release K311 and press a base key; confirm the base keycode returns.

## 5. Bootloader recovery (physical board)

- [ ] Re-enter DFU with the BOOT0/NRST sequence.
- [ ] Reflash the same firmware and confirm USB enumeration again.
- [ ] Record the flash tool, firmware SHA-256, host OS, and date in the release
      log.

## Sign-off

- [ ] All 48 key positions verified against the table.
- [ ] USB enumeration verified.
- [ ] Bootloader entry and recovery verified.
- [ ] No simulated result claimed as HIL.

Tester: ____________________  Board serial: ____________________  Date: __________
