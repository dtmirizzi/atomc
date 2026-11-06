# atomc-keeb (4×12 ortholinear)

::: info Current status
`examples/atomc-keeb` and its IR/QMK sources are seeded. The atomc hardware plugins and full vertical slice are still planned. Renode is a regression aid and is not evidence of USB-HID behavior.
:::

`atomc-keeb` is the larger example fixture: a 48-key ortholinear keyboard with hardware/firmware source and IR intended to exercise the future circuits-to-fabrication pipeline.

## Hardware

- **Layout:** 4×12 ortholinear, 19.05 mm pitch, Kailh MX hot-swap sockets, per-key 1N4148W diodes
- **USB-C** with 5.1 kΩ CC pull-downs and a USBLC6-2SC6 ESD array
- **MCU:** STM32F411CEU6, 8 MHz HSE (QMK ChibiOS), SWD + UART + BOOT0 broken out
- **Test pads:** pogo-reachable pads for VBUS, 3V3, GND, SWDIO, SWCLK, NRST, UART TX/RX, BOOT0, and
  every row/col net — so the printed jig can bring the board up without a soldered header

## Firmware

The fixture contains QMK ChibiOS `keyboard.json` and a default keymap. Generating these from `/keyboard` and `/layout`, and enforcing IR-to-firmware pin agreement with `fw.matrix_pins_match_ir`, are planned plugin work.

Renode can test CPU and supported peripheral behavior when the target path is demonstrated. It is not claimed to validate USB-HID reports or every physical key. Those checks require hardware-in-loop testing.

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
A future sourcing adapter may use public catalogue data; no offer lookup or quote is performed by this fixture today.

## Build it

```bash
cd examples/atomc-keeb
ato build
qmk compile -kb atomc/keeb -km default
atomc build      # requires the not-yet-landed atomc hardware plugins
```
