# atomc-drivetrain

> **This is a modeled fixture, not a buildable design.** It exists to prove the
> atomc system IR is domain-generic — it is not a keyboard and has no `/keyboard`
> node. Nothing here is qualified for a real vehicle, and no claim in this
> directory has been validated on hardware.
>
> **High-voltage work is dangerous.** Reusing a Tesla-type drive-unit power stage
> means DC-link voltages that can kill. This fixture models only the control-side
> board and treats the HV power stage as external; it contains no HV layout,
> isolation, creepage, creepage-distance or safety analysis.

`atomc-drivetrain` is a drop-in control board for a reused Tesla-style PMSM
drive-unit power stage, modeled on the [openinverter.org](https://openinverter.org)
architecture. openinverter is an open-source motor-control firmware/mainboard
project; this fixture borrows its documented **STM32F407VGT6 mainboard MCU** choice
and the general idea of driving a stock Tesla power stage with custom control
electronics. It is an independent model and is not affiliated with or endorsed by
openinverter.org, Tesla, or any part vendor.

## What it models

- A **control-only** board. The stock power stage (six IGBTs) and the HV DC link are
  outside this board; the board supplies gate-drive, current-sense, resolver and
  contactor-control signals.
- The IR is hand-authored. There is no `ato`/atopile source project behind it, and
  no QMK or Renode firmware artifact; `/firmware` records the intended baremetal
  openinverter target with `artifacts: []`.

### Components (`/electrical/components`)

| ref   | mpn            | role                                                                 |
| ----- | -------------- | -------------------------------------------------------------------- |
| U1    | STM32F407VGT6  | MCU, LQFP100, 3.3 V, 168 MHz (documented openinverter mainboard MCU) |
| U2-U4 | UCC21520       | 3× isolated dual-channel half-bridge gate drivers (isolated domain)  |
| U5-U7 | INA240A2       | 3× phase-current sense amplifiers over the power-stage shunts        |
| U8    | AMC1311        | isolated DC-link voltage sense amplifier (isolated domain)           |
| U9    | SN65HVD230     | CAN transceiver                                                       |
| U10   | LM5164         | 12 V → 5 V buck                                                       |
| U11   | AP2112K-3.3    | 3.3 V LDO                                                             |
| U12   | MCP6002        | resolver signal buffer (dual op-amp)                                 |
| U13   | VNLD5090       | low-side driver: main contactor                                      |
| U14   | VNLD5090       | low-side driver: precharge                                           |
| J1    | 640456-3       | 12 V LV input header (TE, 3-pos)                                     |
| J2    | 2199230-3      | resolver header (TE, 3-pos)                                          |
| J3    | 640456-6       | CAN + NTC + gate-drive pass-through header (TE, 6-pos)              |

### Other nodes

- `/electrical/nets` — 20 nets including `CAN_H`/`CAN_L` (`diff`),
  `ISENSE_U/V/W`, `VSUPPLY_U/V/W` and `HV_VSENSE` (`power`), and resolver/contactor
  signals. Every net connects at least two pins; the isolated-domain driver-side
  pins make `VSUPPLY_U/V/W` resolve.
- `/electrical/assertions` — two synthetic assertions recorded as `pass`
  (`assert:phase_current`, `assert:can_term`). They are labels for the modeled
  intent, not results of a real electrical rule check.
- `/firmware` — one target `fw:openinverter` (baremetal, no artifacts) with `can`,
  `timer` and three `other` ADC peripherals.
- `/layout` — 120×80 mm, 4-layer outline; 12 bottom-side pogo test pads; 4 mounting
  holes; placements for U1, U9 and J1 only.
- `/mechanical` — PCB bbox, tray enclosure (2 mm wall, 1.5 mm clearance). **No plate
  and no jig**, because there are no switches.
- `/sourcing` — 17 BOM lines at qty 2, per-unit budget 12000¢ / total 24000¢.
  LCSC codes are left `null` where they were not known; offers are synthetic
  `example.com` records.
- `/fabrication` — 4-layer 120×80×1.6 mm ENIG PCB, qty 2, `quotes: []`.
- There is deliberately **no** `/keyboard`, `/orders`, `/simulation` or `/gates`
  node in the committed file.

## Expected gate outcomes

Outcomes below are what the current daemon and built-in plugins produce for this
IR. Run every gate directly with the snippet in "Build and check it" to reproduce;
the "Notes" column calls out where the brief's expectation ("all `fw.*` gates
SKIP") differs from observed behaviour.

| Gate                                     | Outcome | Why                                                                                          |
| ---------------------------------------- | ------- | -------------------------------------------------------------------------------------------- |
| `gate:erc.no_unconnected`                | PASS    | all 20 nets have ≥ 2 connected pins                                                          |
| `gate:erc.assertions`                    | PASS    | both recorded assertions are `pass`                                                          |
| `gate:layout.testpads.min_count`         | PASS    | 12 pogo pads ≥ 8                                                                             |
| `gate:layout.testpads.nets_covered`      | SKIP    | `/keyboard` absent → matrix nets unknown                                                     |
| `gate:bom.all_in_stock`                  | PASS    | chosen offers cover qty (2) and MOQ                                                          |
| `gate:bom.cost_under_budget`             | PASS    | 9940¢ extended, 4970¢/unit vs 24000¢ / 12000¢ budget                                         |
| `gate:bom.lead_time_under_days`          | PASS    | max chosen lead time 7 ≤ 14-day default cap                                                  |
| `gate:fab.quote_under_budget`            | SKIP    | no quotes fetched (`quotes: []`)                                                             |
| `gate:mech.plate_switch_cutouts_14mm`    | SKIP    | `/keyboard/keys`: no switch references found                                                 |
| `gate:mech.case_usb_cutout_aligned`      | SKIP    | `/keyboard/keys`: no switch references found (plate derivation is shared)                    |
| `gate:mech.pogo_spacing_ge_2p54`         | SKIP    | `/keyboard/keys`: no switch references found (plate derivation is shared)                    |
| `gate:mech.jig_no_collision`             | SKIP    | `/keyboard/keys`: no switch references found (plate derivation is shared)                    |
| `gate:mech.enclosure_clearance`          | SKIP    | `/keyboard/keys`: no switch references found (plate derivation is shared)                    |
| `gate:fw.renode_boot`                    | SKIP    | STM32F407VGT6 is not covered by the generated `stm32f4.repl` platform (only STM32F411)       |
| `gate:fw.matrix_scan`                    | SKIP    | declared-not-implemented; requires HIL + pogo fixture                                        |
| `gate:fw.matrix_pins_match_ir`           | FAIL    | **deviates from this brief's expectation**: the plugin FAILs when `/keyboard` is absent      |
| `gate:fw.qmk_compile`                    | FAIL    | **deviates from this brief's expectation**: with a QMK toolchain present it FAILs on absent `/keyboard` (without the toolchain it would SKIP) |

Two additional honesty notes from the end-to-end run (recorded in full in
`docs/plan/handoffs/WP-6.1.md`):

- The `renode:generate` watch completes as an honest no-op: this fixture has no
  firmware artifact, so there is nothing to emulate (the watch returns a
  SKIP-shaped result, mirroring the gate semantics).
- No gate returns `ERROR` for this fixture; a full daemon DAG run settles all 26
  nodes and exits 0.

## Build and check it

Validate the IR with core-ir (Python) and the contract tests (TypeScript):

```bash
# from the repository root
uv sync --all-packages
uv run python -c "from atomc_core_ir import SystemIR; SystemIR.load('examples/atomc-drivetrain/system_ir.json')"
pnpm --filter @atomc/contract-tests test
```

Run the daemon gate runner over a throwaway copy of the IR (this does not modify
the committed file):

```bash
uv run python - <<'PY'
import asyncio, shutil, tempfile
from pathlib import Path
from atomcd.ir_store import IRStore
from atomcd.events import EventBus
from atomcd.gates import GateRunner
from atomcd.plugins.discovery import build_registry

tmp = Path(tempfile.mkdtemp())
shutil.copy("examples/atomc-drivetrain/system_ir.json", tmp / "system_ir.json")

async def main():
    store = IRStore(tmp); store.load()
    events = EventBus()
    registry = build_registry(tmp, store=store, events=events)
    for r in sorted(await GateRunner(registry=registry, store=store, events=events).run(),
                    key=lambda x: x["id"]):
        print(f"{r['id']}\t{r['status']}\t{r['summary']}")

asyncio.run(main())
PY
```

Run the full daemon build path (note the `renode:generate` watch failure described
above):

```bash
# build the CLI once, from the repository root
pnpm --filter @atomc/cli build

cd examples/atomc-drivetrain
uv run atomcd serve --project .    # in one shell
# in another shell, once the daemon is healthy:
node ../../apps/atomc-cli/dist/index.js build --project .
```
