# atomc-drivetrain (openinverter-style drive-unit control board)

::: warning Modeled fixture, not a buildable design
`examples/atomc-drivetrain` is a **model**. It is not a manufacturable board, it is
not qualified for a real vehicle, and nothing in it has been validated on hardware.
**HV work is dangerous** — a reused drive-unit power stage presents lethal DC-link
voltages. This fixture models only control-side electronics and treats the HV power
stage as external.
:::

`atomc-drivetrain` is an openinverter-style control board for a reused Tesla-type
PMSM drive unit. It is the third atomc example and exists to prove the
[system IR](/architecture/ir) is not keyboard-shaped: the domain-generic nodes
(`/electrical`, `/firmware`, `/layout`, `/mechanical`, `/sourcing`, `/fabrication`)
fully describe a traction-inverter control board, and the optional `/keyboard` node
is **absent**.

The fixture is modeled on [openinverter.org](https://openinverter.org) — an
open-source motor-control project — and borrows its documented STM32F407VGT6
mainboard MCU. It is an independent model and is not affiliated with or endorsed by
openinverter.org, Tesla, or any part vendor.

## What the IR contains

- **`/electrical`** — 17 components: STM32F407VGT6 MCU, three UCC21520 isolated
  half-bridge gate drivers, three INA240A2 phase-current sense amplifiers, an
  AMC1311 isolated DC-link sense amp, an SN65HVD230 CAN transceiver, LM5164 buck,
  AP2112K-3.3 LDO, MCP6002 resolver buffer, two VNLD5090 contactor/precharge
  drivers, and three TE headers. Twenty nets (CAN differential pair, phase-current
  and phase-voltage nets, resolver signals, contactor coils) each connect at least
  two pins.
- **`/firmware`** — one `fw:openinverter` baremetal target on `cortex-m4` with no
  build artifacts, plus `can`, `timer`, and three ADC `other` peripherals.
- **`/layout`** — 120×80 mm 4-layer outline, 12 bottom-side pogo test pads, four
  mounting holes, and minimal placements.
- **`/mechanical`** — PCB bbox and a tray enclosure. There is no plate and no jig.
- **`/sourcing`** — 17 BOM lines at build qty 2 with synthetic offers and a
  12000¢/unit, 24000¢ total budget.
- **`/fabrication`** — 4-layer ENIG PCB spec at qty 2, with `quotes: []`.

## Gates: generic IR, honest skips

Because the IR is not a keyboard, the keyboard-specific gates skip against absent
data instead of failing the board:

| Gate family                        | Outcome on this fixture                                            |
| ---------------------------------- | ------------------------------------------------------------------ |
| `erc.*`, `layout.testpads.*`       | PASS from real net/pad data; `nets_covered` SKIPs (no keyboard)    |
| `bom.*`                            | PASS against the recorded offers and budget                        |
| `fab.quote_under_budget`           | SKIP — no quotes fetched                                           |
| `mech.*`                           | SKIP — "no switch references found"                                |
| `fw.renode_boot`, `fw.matrix_scan` | SKIP — MCU not in the generated platform; matrix scan not built    |
| `fw.matrix_pins_match_ir`, `fw.qmk_compile` | FAIL — the QMK plugin requires `/keyboard` and does not skip on its absence |

The last row is a known mismatch with the original brief ("all `fw.*` gates SKIP");
it is recorded rather than papered over in
`docs/plan/handoffs/WP-6.1.md`. The `renode:generate` watch also fails without an
ELF artifact, which aborts a full DAG run before later gates execute.

## Validate and inspect

```bash
# from the repository root
uv sync --all-packages
uv run python -c "from atomc_core_ir import SystemIR; SystemIR.load('examples/atomc-drivetrain/system_ir.json')"
pnpm --filter @atomc/contract test

# run every gate directly against a throwaway copy of the IR
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

See [`examples/atomc-drivetrain/README.md`](https://github.com/dtmirizzi/atomc/tree/main/examples/atomc-drivetrain)
for the full component table and gate notes.
