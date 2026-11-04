# atomc-keeb (4×12 ortholinear)

::: info Planned
`examples/atomc-keeb` is seeded in Phase 1 (WP-1.6); the full vertical slice lands in Phase 4 (WP-4.5).
:::

`atomc-keeb` is the flagship example: a **48-key ortholinear keyboard** that is meant to be a real,
orderable end-to-end product. It exercises every plugin — circuits, firmware, enclosure, jig, sourcing
and orders.

## Hardware

- **Layout:** 4×12 ortholinear, 19.05 mm pitch, Kailh MX hot-swap sockets, per-key 1N4148W diodes
- **USB-C** with 5.1 kΩ CC pull-downs and a USBLC6-2SC6 ESD array
- **MCU:** STM32F411CEU6, 8 MHz HSE (QMK ChibiOS), SWD + UART + BOOT0 broken out
- **Test pads:** pogo-reachable pads for VBUS, 3V3, GND, SWDIO, SWCLK, NRST, UART TX/RX, BOOT0, and
  every row/col net — so the printed jig can bring the board up without a soldered header

## Firmware

QMK (latest `qmk_firmware` master, ChibiOS). The `keyboard.json` and default keymap are generated from
the `/keyboard` and `/layout` IR nodes in Phase 4 — matrix pins, diode direction, layout geometry and
USB VID/PID all come from the IR, which is what the `fw.matrix_pins_match_ir` gate enforces.

Renode tests inject matrix GPIO and assert on QMK debug UART output and the HID report buffer, so
[`fw.matrix_scan`](/architecture/dag-gates) proves every key press maps to the right keycode.

## Enclosure and jig

`plugin-cad-jig` (build123d) generates three solids from the layout:

1. **Switch plate** — 14 mm cutouts at 19.05 mm pitch, taken from switch placements.
2. **Case** — tray mount with a USB-C cutout aligned to the connector.
3. **Pogo-pin bed-of-nails jig** — P75 receptacles, alignment pins on the mounting holes, clamshell
   lid; checked for spacing ≥ 2.54 mm and no collisions.

Exports are `.step`, `.stl` and `.glb`. The `.glb` is rendered by the `<model-viewer>` component below
once the artifacts exist.

<ClientOnly>
  <ModelViewer
    src="/atomc/models/atomc-keeb-jig.glb"
    alt="atomc-keeb pogo-pin test jig"
  />
</ClientOnly>

## Sourcing

Budget gate `bom.cost_under_budget` is **4500¢** per board at qty 5, excluding switches and keycaps.
Offers come from the public LCSC/JLCPCB catalogues, so no vendor keys are needed.

## Build it

```bash
cd examples/atomc-keeb
ato build
qmk compile -kb atomc/keeb -km default
atomc build      # planned: full DAG + gates
```
