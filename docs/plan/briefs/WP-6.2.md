# WP-6.2 `example-cannode` — minimal CAN sensor node fixture

Read `_common.md`, then the WP-6.1 brief context (same domain-generality goal), `examples/atomc-pad/**`, and the frozen core-IR models. A deliberately **small, 2-layer, cheap** non-keyboard example: a bench CAN sensor node. Facts are fixed by this brief; do not invent others.

## Owned paths
- `examples/atomc-cannode/**`
- `docs/examples/atomc-cannode.md` + `docs/examples/index.md` (add the entry; WP-6.1 adds theirs — keep your line isolated)
- `docs/plan/handoffs/WP-6.2.md`

The contract round-trip list is WP-6.1's to extend with `"atomc-drivetrain"`; you may add `"atomc-cannode"` to the same `EXAMPLES` array (keep your edit to one line — expect a trivial merge).

## The fixture (facts fixed by this brief)

**Board**: a 2-layer CAN environmental sensor node for bench integration.

Components (`/electrical/components`):
| ref | mpn | role |
|---|---|---|
| U1 | STM32G0B1CBT6 | MCU, LQFP48, 3.3 V |
| U2 | SN65HVD230 | CAN FD-capable transceiver (used at classic CAN rates here) |
| U3 | SHT40-AD1B | I²C temperature/humidity sensor |
| U4 | AP2112K-3.3 | 3.3 V LDO from 5 V |
| J1 | 640456-4 | 4-pos header: 5 V, GND, CAN_H, CAN_L (TE) |

Nets: `5V`, `GND`, `3V3`, `CAN_H`+`CAN_L` (class `diff`), `I2C_SDA`, `I2C_SCL`. Pins 1:1; all nets ≥2 pins. One passing assertion: "I²C pull-ups present" (status pass).

**`/firmware`**: target `fw:cannode` — mcu `STM32G0B1CBT6`, core `cortex-m0plus`, framework `baremetal`, source_dir `firmware/`, artifacts `[]`; peripherals: `can`, `i2c` (SHT40), `timer`. All `fw.*` gates SKIP honestly.

**`/layout`**: outline 40×25 mm, 2 layers, 8 bottom `pogo` test pads (3V3, GND, CAN_H, CAN_L, I2C_SDA, I2C_SCL, 5V, plus one on U1 SWDIO — label it), 2 mounting holes, placements for U1-U4 + J1.

**`/mechanical`**: `pcb_bbox` matching; **no plate/jig/enclosure** — all keyboard/mech-specific gates SKIP. Record exact evidence in the README table.

**`/sourcing`**: `build_qty` 5, budget per_unit 1500 / total 7500; one bom entry per component with one synthetic offer (example.com URLs; unit prices roughly: U1 $2.8, U2 $1.2, U3 $2.5, U4 $0.5, J1 $0.4; stock comfortably ≥ qty), chosen refs set, `alternates` `[]`. `bom.*` gates must PASS — verify and record.

No `/keyboard`, `/fabrication`, `/orders`, `/simulation`, `/gates` nodes.

## Deliverables
1. `examples/atomc-cannode/{system_ir.json,README.md,atomc.config.ts}`; IR validates via both Python and TS parsers (contract round-trip list extended by one line).
2. README: what it is (fixture), expected gate table (PASS from real data / SKIP with reasons), exact CLI commands, and a note that a second real example proves domain generality beyond keyboards.
3. E2E honesty check recorded in the handoff (daemon run over the project; actual gate outcomes table). Report (do not fix) any ERROR where a SKIP was expected.
4. Handoff: exact commands, expected-vs-actual table, deviations, root changes needed (should be none).

## Definition of done
- Contract tests stay green including the new example; Python + TS round-trip passes.
- No invented facts; conventional commits; push `wp/6.2-example-cannode`; do not merge.
