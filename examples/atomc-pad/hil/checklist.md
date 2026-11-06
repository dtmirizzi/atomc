# atomc-pad hardware-in-the-loop (HIL) checklist

> **Physical hardware only.** Every item below requires the assembled atomc-pad
> board plus the pogo-pin jig. Simulation (Renode) is a regression aid and does
> **not** prove USB HID, matrix scan correctness, or bootloader recovery. Do not
> mark a simulated run as a HIL pass.

## Prerequisites

- [ ] Assembled `atomc-pad` PCB (STM32F411CEU6, 3x3 COL2ROW matrix).
- [ ] Pogo-pin jig for the 15 bottom-side test pads (rows `B12/B13/B14`, cols
      `A0/A1/A2`, UART `A9/A10`, SWD, NRST, BOOT0).
- [ ] USB-C cable and a host with `lsusb` (Linux/macOS) and `hid_listen` or
      `qmk console`.
- [ ] DFU tool (`dfu-util`) or SWD tool (`openocd`) for flashing/recovery.
- [ ] Multimeter for continuity and rail checks.

## 1. Bench inspection (physical board)

- [ ] Verify no shorts between 3V3 and GND before applying power.
- [ ] Verify 5.1 kΩ CC1/CC2 pull-downs are populated.
- [ ] Verify one 1N4148W per switch and COL2ROW orientation.
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
- [ ] Confirm host enumeration of VID:PID `0xFEED:0x0001`.
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

| Key | Row | Col | Base keycode | Utility layer keycode | Test |
|-----|----:|----:|--------------|-----------------------|------|
| K00 | 0 | 0 | `KC_1` | `KC_MUTE` | [ ] **[pogo]** |
| K01 | 0 | 1 | `KC_2` | `KC_VOLD` | [ ] **[pogo]** |
| K02 | 0 | 2 | `KC_3` | `KC_VOLU` | [ ] **[pogo]** |
| K10 | 1 | 0 | `KC_4` | `KC_MPRV` | [ ] **[pogo]** |
| K11 | 1 | 1 | `KC_5` | `KC_MPLY` | [ ] **[pogo]** |
| K12 | 1 | 2 | `KC_6` | `KC_MNXT` | [ ] **[pogo]** |
| K20 | 2 | 0 | `KC_7` | `KC_BRIU` | [ ] **[pogo]** |
| K21 | 2 | 1 | `KC_8` | `KC_BRID` | [ ] **[pogo]** |
| K22 | 2 | 2 | `KC_9` (tap) / layer key (hold) | `_______` | [ ] **[pogo]** |

### Layer test

- [ ] Hold K22 (layer tap) and press K00-K21; confirm the utility-layer keycodes
      in the table above.
- [ ] Release K22 and press K22 again; confirm `KC_9` on tap.

## 5. Bootloader recovery (physical board)

- [ ] Re-enter DFU with the BOOT0/NRST sequence.
- [ ] Reflash the same firmware and confirm USB enumeration again.
- [ ] Record the flash tool, firmware SHA-256, host OS, and date in the release
      log.

## Sign-off

- [ ] All key positions verified against the table.
- [ ] USB enumeration verified.
- [ ] Bootloader entry and recovery verified.
- [ ] No simulated result claimed as HIL.

Tester: ____________________  Board serial: ____________________  Date: __________
