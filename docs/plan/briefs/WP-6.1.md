# WP-6.1 `example-drivetrain` — openinverter-style Tesla drive-unit control board fixture

Read `_common.md`, then: `examples/atomc-pad/**` (the established fixture pattern), `packages/core-ir/python/src/atomc_core_ir/{document,electrical,firmware,layout,mechanical,sourcing,fabrication}.py` (the frozen models — the IR is domain-generic; `/keyboard` is optional and must be **absent** here), the plugin manifests for the gates' expected SKIP behavior on non-keyboard IR, and `docs/architecture/contracts/ir-schema.md`.

This fixture proves atomc is not keyboard-shaped: a traction-inverter control board, modeled on the **openinverter** architecture (openinverter.org — open-source motor-control firmware) driving a Tesla-type PMSM drive unit whose stock power stage is reused. The hardware facts below are fixed by this brief; do not invent additional parts, values or claims. The README must state plainly: this is a modeled fixture, not a buildable safety-critical design; HV work is dangerous; nothing here is qualified for a real vehicle.

## Owned paths
- `examples/atomc-drivetrain/**`
- `tests/contract/ts/roundtrip.test.ts` (add `"atomc-drivetrain"` to EXAMPLES)
- `tests/contract/ts/fixtures.test.ts` (add the example dir if its assertions apply; adapt honestly)
- `docs/examples/atomc-drivetrain.md` (new walkthrough page) + `docs/examples/index.md` (add the entry)
- `docs/plan/handoffs/WP-6.1.md`

Do not edit plugins, packages, root files or the other examples. If a model rejects a fact below, stop and report rather than coercing.

## The fixture (facts fixed by this brief)

**Board**: drop-in control board for a reused Tesla-style drive-unit power stage. All control-side power; the HV stage is external.

**Components** (`/electrical/components`, control domain unless noted):
| ref | mpn | role |
|---|---|---|
| U1 | STM32F407VGT6 | MCU, LQFP100, 3.3 V, 168 MHz (the documented openinverter mainboard MCU) |
| U2-U4 | UCC21520 | 3× isolated dual-channel half-bridge gate drivers for the six IGBTs (isolated domain) |
| U5-U7 | INA240A2 | 3× phase-current sense amplifiers over the power-stage shunts |
| U8 | AMC1311 | isolated DC-link voltage sense amp (isolated domain) |
| U9 | SN65HVD230 | CAN transceiver |
| U10 | LM5164 | 12 V→5 V buck |
| U11 | AP2112K-3.3 | 3.3 V LDO |
| U12 | MCP6002 | resolver signal buffer (dual op-amp) |
| U13-U14 | VNLD5090 | 2× low-side drivers: main contactor + precharge |
| J1 | 640456-3 | 12 V LV input header (TE, 3-pos) |
| J2 | 2199230-3 | resolver header (TE, 3-pos) |
| J3 | 640456-6 | CAN + NTC + gate-drive pass-through header |

Nets (`/electrical/nets`): `LV_12V`, `LV_GND`, `3V3`, `GND`, `5V`, `CAN_H`+`CAN_L` (class `diff`), `ISENSE_U/V/W`, `VSUPPLY_U/V/W` (class power), `RESOLVER_SIN`, `RESOLVER_COS`, `RESOLVER_EXC`, `HV_VSENSE` (class power), `NTC_PWR`, `CONT_COIL`, `PRECHG_COIL`. Pins reference nets 1:1; every net has ≥2 pins except the isolated-domain ones which must still resolve (add the driver-side pins). Two passing assertions (`/electrical/assertions`): "every phase has a current sense path" and "CAN is terminated" (status pass).

**`/firmware`**: one target `fw:openinverter` — mcu `STM32F407VGT6`, core `cortex-m4`, framework `baremetal`, source_dir `firmware/`, build_cmd null, artifacts `[]`; peripherals: `can` (with signals TX/RX), `timer` (PWM), 3× `other` (resolver ADC, current-sense ADC, NTC ADC). `fw.*` gates SKIP honestly (no keyboard, no QMK, no artifacts).

**`/layout`**: outline 120×80 mm rectangle, 4 layers, `source` null, 12 bottom-side `pogo` test pads (≥8 for the min-count gate) on: 3V3, GND, CAN_H, CAN_L, ISENSE_U/V/W, RESOLVER_SIN/COS; 4 mounting holes; placements minimal (U1, U9, J1 with plausible coordinates).

**`/mechanical`**: `pcb_bbox` matching the outline; `enclosure` tray, wall 2 mm, clearance 1.5 mm; **no plate, no jig** — the keyboard-specific mech gates must SKIP with "no switch references found"-style evidence. Record the exact SKIP evidence in the README's expected-outcomes table.

**`/sourcing`**: `build_qty` 2, currency USD, budget per_unit 12000 / total 24000; one `bom:` entry per component (mpn, lcsc where the part genuinely has one — leave `lcsc` null where unsure, do not invent LCSC codes), each with one synthetic offer (example.com URL pattern like the pad fixture, plausible stock ≥ qty×moq, unit prices roughly: U1 $11, UCC21520 $4.50, INA240A2 $2, AMC1311 $5.50, SN65HVD230 $1.2, LM5164 $3.8, AP2112K $0.5, MCP6002 $0.6, VNLD5090 $3, headers $0.3-0.8), `chosen_offer_ref` set, `alternates` one entry for U1. The three `bom.*` gates must PASS against this data — verify and record.

**`/fabrication`**: pcb spec 4 layers, 120×80, 1.6 mm, ENIG, green, qty 2; `quotes: []` → `fab.quote_under_budget` SKIPs ("no quotes fetched"). No `/orders`, no `/simulation`, no `/gates` node.

## Deliverables
1. `examples/atomc-drivetrain/{system_ir.json,README.md,atomc.config.ts}` (copy the config pattern from atomc-pad). The IR must validate with `uv run python -c "from atomc_core_ir import SystemIR; SystemIR.load('examples/atomc-drivetrain/system_ir.json')"` (find the exact load API from core-ir) and through the TS parser in the contract tests.
2. README: what it is (modeled fixture, openinverter attribution, safety disclaimer), the full expected gate-outcome table (which PASS from real IR data, which SKIP and why), and the exact commands to build it with the CLI.
3. Contract round-trip wired; `docs/examples/atomc-drivetrain.md` walkthrough + index entry.
4. E2E honesty check (in your worktree, recorded in the handoff): run the daemon over this project (`atomcd serve` per the WP-4.5/WP-3.10 patterns or the CLI build path) and record the actual gate outcomes — every SKIP must trace to absent data, every PASS to IR data. If any gate ERRORs where it should SKIP, report it in the handoff (do not edit the plugin).
5. Handoff: exact commands, expected-vs-actual gate table, deviations, root changes needed (should be none).

## Definition of done
- Contract round-trips pass for the new example on both languages; `uv run pytest -q` and `pnpm --filter @atomc/contract test` (or the repo's contract command) stay green.
- No invented parts/claims beyond this brief; the safety disclaimer is prominent.
- Conventional commits; push `wp/6.1-example-drivetrain`; do not merge.
