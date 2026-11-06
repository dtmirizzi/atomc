# atomc-cannode

A deliberately small, cheap, **2-layer CAN environmental sensor node** for bench
integration. It is the second real example in the [atomc](../../PLAN.md) repository
and exists to prove the IR and gate layer are **domain-generic, not keyboard-shaped**:
it has no `/keyboard` node, no switch matrix and no enclosure.

It is a **modeled fixture**, not a manufactured design. The electrical pin maps are
simplified seed numbering (the MCU/transceiver functions are named, not layout-bound).

## What it is

| Ref | MPN           | Role                                                         |
| --- | ------------- | ------------------------------------------------------------ |
| U1  | STM32G0B1CBT6 | MCU, LQFP48, 3.3 V, I²C master + FDCAN                       |
| U2  | SN65HVD230    | CAN transceiver (CAN FD-capable part, used at classic rates) |
| U3  | SHT40-AD1B    | I²C temperature / humidity sensor                            |
| U4  | AP2112K-3.3   | 3.3 V LDO from 5 V                                           |
| J1  | 640456-4 (TE) | 4-position header: 5 V, GND, CAN_H, CAN_L                    |

Nets: `5V`, `GND`, `3V3`, `CAN_H`/`CAN_L` (class `diff`), `I2C_SDA`, `I2C_SCL`,
plus the single debug net `SWDIO` broken out for bring-up (see limitations below).

One recorded atopile assertion: **"I²C pull-ups present"** (status `pass`).

## IR contents

- `/electrical` — U1–U4 and J1 with named pins, the nets above, one passing assertion.
- `/firmware` — one `fw:cannode` target (`STM32G0B1CBT6`, `cortex-m0plus`, `baremetal`,
  `source_dir: firmware/`, no artifacts); peripherals `can`, `i2c`, `timer`.
- `/layout` — 40 × 25 mm 2-layer outline, placements for U1–U4 + J1, eight bottom-side
  `pogo` test pads (3V3, GND, CAN_H, CAN_L, I2C_SDA, I2C_SCL, 5V, SWDIO), two mounting holes.
- `/mechanical` — `pcb_bbox` only; **no plate, jig or enclosure**.
- `/sourcing` — `build_qty` 5, budget 1500 ¢/unit and 7500 ¢ total, one BOM line per
  component with one synthetic `example.com` offer each.

## Expected gate outcomes

Observed with the real daemon gate runner over this project (see the handoff for the
exact command). "PASS" is driven by IR data; "SKIP" always carries a reason.

| Gate                             | Status | Why                                                       |
| -------------------------------- | ------ | --------------------------------------------------------- |
| `bom.all_in_stock`               | PASS   | 5 BOM lines, chosen offers cover qty (5) and MOQ          |
| `bom.cost_under_budget`          | PASS   | 3700 ¢ extended / 740 ¢ per unit vs 7500 / 1500 budgets   |
| `bom.lead_time_under_days`       | PASS   | max chosen lead 7 d ≤ 14 d default cap                    |
| `erc.assertions`                 | PASS   | the single recorded assertion is `pass`                   |
| `layout.testpads.min_count`      | PASS   | 8 test pads ≥ 8 minimum                                   |
| `erc.no_unconnected`             | FAIL   | `net:SWDIO` has one MCU pin (see limitations)             |
| `fw.matrix_pins_match_ir`        | FAIL   | no `/keyboard` node — the qmk gate requires one           |
| `fw.qmk_compile`                 | FAIL   | no `/keyboard` node (SKIPs instead when QMK is absent)    |
| `fw.matrix_scan`                 | SKIP   | matrix injection unproven; needs HIL board + pogo fixture |
| `fw.renode_boot`                 | SKIP   | `STM32G0B1CBT6` outside the modelled `STM32F411` platform |
| `layout.testpads.nets_covered`   | SKIP   | `/keyboard` absent, matrix nets unknown                   |
| `fab.quote_under_budget`         | SKIP   | no quotes fetched (`/fabrication` absent)                 |
| `mech.plate_switch_cutouts_14mm` | SKIP   | no switch references found                                |
| `mech.case_usb_cutout_aligned`   | SKIP   | no switch references found                                |
| `mech.pogo_spacing_ge_2p54`      | SKIP   | no switch references found                                |
| `mech.jig_no_collision`          | SKIP   | no switch references found                                |
| `mech.enclosure_clearance`       | SKIP   | no switch references found                                |

### Known limitations (honest, not engineered away)

- **`erc.no_unconnected` FAILs on `net:SWDIO`.** The brief fixes the component list to
  U1–U4 and J1 but also asks for an eighth test pad on U1's SWDIO. SWDIO is a debug net
  with a single electrical pin on this board, so the pure ERC gate (which counts only
  component pins, not test pads) reports one net with fewer than two pins. The other
  seven nets each connect ≥2 pins. Keeping the SWDIO pad documents the real single-point
  debug net rather than hiding it.
- **`fw.matrix_pins_match_ir` and `fw.qmk_compile` FAIL, not SKIP, without `/keyboard`.**
  The qmk plugin's matrix-pin gate and compile gate return `FAIL` when the IR has no
  `/keyboard` node; on a host _without_ QMK the compile gate short-circuits to `SKIP`
  first. Renode (`fw.renode_boot` / `fw.matrix_scan`) and all mechanical gates SKIP
  honestly for this non-keyboard fixture.

## Inspect it

```bash
# Python round-trip / validation
uv run python -c "from atomc_core_ir import SystemIR; SystemIR.load('examples/atomc-cannode/system_ir.json')"

# TS + Python contract round-trips (includes this example)
pnpm install --frozen-lockfile
pnpm --filter @atomc/contract-tests contract

# Real daemon gate run
uv sync --all-packages
uv run atomcd serve -p examples/atomc-cannode   # then run gates over RPC
```

BOM/lead-time gates are the real data-backed checks here; the keyboard-specific gates
are expected to SKIP (or FAIL, see above) because this board has no keyboard.
