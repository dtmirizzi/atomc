# atomc-cannode (CAN sensor node)

`examples/atomc-cannode` is a deliberately small, 2-layer **CAN environmental sensor
node** used for bench integration. It is the second real example and the one that
demonstrates the IR and the gate layer are **domain-generic rather than keyboard-shaped**:
there is no `/keyboard` node, no switch matrix and no enclosure.

It is a modeled fixture — the electrical pin maps use simplified seed numbering and the
sourcing offers are synthetic — not a manufacturable design.

## Hardware

- **MCU:** STM32G0B1CBT6 (LQFP48, 3.3 V) with I²C and FDCAN
- **Transceiver:** SN65HVD230 (CAN FD-capable part used at classic CAN rates)
- **Sensor:** SHT40-AD1B I²C temperature/humidity sensor
- **Regulator:** AP2112K-3.3 LDO from 5 V
- **Header:** TE 640456-4 (5 V, GND, CAN_H, CAN_L)
- **Test pads:** eight bottom-side pogo pads — 3V3, GND, CAN_H, CAN_L, I2C_SDA,
  I2C_SCL, 5V and SWDIO

## The IR

- `/electrical` — five components with named pins, the CAN/power/I²C nets, one passing
  assertion ("I²C pull-ups present").
- `/firmware` — a single `fw:cannode` baremetal target and `can`/`i2c`/`timer` peripherals.
- `/layout` — a 40 × 25 mm 2-layer outline, placements and the eight pogo test pads.
- `/mechanical` — `pcb_bbox` only; no plate, jig or enclosure.
- `/sourcing` — `build_qty` 5, a 1500 ¢/unit / 7500 ¢ total budget and one synthetic offer
  per BOM line.

## Gates

Every gate runs over the real IR. The three `bom.*` gates PASS from the sourcing data and
`erc.assertions` / `layout.testpads.min_count` PASS. The keyboard- and CAD-specific gates
SKIP with exact reasons ("no switch references found", "no quotes fetched"). Two gates
report `FAIL` honestly: `erc.no_unconnected` for the single-pin `SWDIO` debug net, and the
qmk matrix-pin / compile gates because there is no `/keyboard` node. See the example's
[README](https://github.com/dtmirizzi/atomc/tree/main/examples/atomc-cannode) and the
WP-6.2 handoff for the full table.

## Inspect it

```bash
uv run python -c "from atomc_core_ir import SystemIR; SystemIR.load('examples/atomc-cannode/system_ir.json')"
pnpm --filter @atomc/contract-tests contract
```
