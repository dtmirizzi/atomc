# WP-6.2 — example-cannode handoff

## What was built

`examples/atomc-cannode` — a deliberately small, 2-layer **CAN environmental sensor
node** fixture and the second non-keyboard example. It proves the frozen IR and the
gate layer are domain-generic: the project has **no `/keyboard`, `/fabrication`,
`/orders`, `/simulation` or `/gates` node**.

- `examples/atomc-cannode/system_ir.json` — hand-authored IR: five components
  (U1 STM32G0B1CBT6, U2 SN65HVD230, U3 SHT40-AD1B, U4 AP2112K-3.3, J1 640456-4), the
  `5V`/`GND`/`3V3`/`CAN_H`/`CAN_L`/`I2C_SDA`/`I2C_SCL` nets plus a debug `SWDIO` net,
  one passing assertion ("I²C pull-ups present"); a `fw:cannode` baremetal target with
  `can`/`i2c`/`timer` peripherals; a 40 × 25 mm 2-layer layout with 8 bottom pogo test
  pads, 2 mounting holes and placements for U1–U4 + J1; a `pcb_bbox`-only `/mechanical`
  node; and a 5-quantity `/sourcing` node with one synthetic offer per BOM line.
- `examples/atomc-cannode/README.md` — fixture description, expected/actual gate table,
  limitations and exact inspect commands.
- `examples/atomc-cannode/atomc.config.ts` — CLI/daemon config (budget gate, sourcing).
- `docs/examples/atomc-cannode.md` + a one-row entry in `docs/examples/index.md`.
- `tests/contract/ts/roundtrip.test.ts` — `"atomc-cannode"` added to the `EXAMPLES`
  array (one line; WP-6.1 owns the drivetrain addition).

## How to verify (exact commands)

```bash
cd /Users/dtmirizzi/.herdr/worktrees/atomc/wp-6-2-example-cannode

# 1. Python model load / referential integrity
uv run python -c "from atomc_core_ir import SystemIR; SystemIR.load('examples/atomc-cannode/system_ir.json'); print('ok')"

# 2. Cross-language contract round-trips (now covers atomc-cannode)
pnpm install --frozen-lockfile
pnpm --filter @atomc/core-ir build          # contract tests need the TS dist
pnpm --filter @atomc/contract-tests test     # 3 files / 32 tests
pnpm --filter @atomc/contract-tests typecheck
pnpm --filter @atomc/contract-tests lint
pnpm exec biome check examples/atomc-cannode tests/contract/ts/roundtrip.test.ts

# 3. Real daemon gate run over the project (drives the GateRunner directly)
uv sync --all-packages
uv run python - <<'PY'
import asyncio
from pathlib import Path
from atomcd.config import DaemonConfig
from atomcd.events import EventBus
from atomcd.gates import GateRunner
from atomcd.ir_store import IRStore
from atomcd.plugins.discovery import build_registry

project = Path("examples/atomc-cannode").resolve()
store = IRStore(project); store.load()
events = EventBus()
registry = build_registry(project, store=store, events=events)
gates = GateRunner(registry=registry, store=store, events=events)
for r in sorted(asyncio.run(gates.run()), key=lambda x: x["id"]):
    print(f'{r["id"]:35s} {r["status"]:5s} {r["summary"]}')
PY
```

## Expected vs actual gate outcomes

Run in this worktree on 2026-11-06 (Node 25, macOS arm64, `uv sync --all-packages`).
QMK was **present** on this machine, `/fabrication` and `/keyboard` were absent.

| Gate                                  | Expected (brief)   | Actual | Note                                             |
| ------------------------------------- | ------------------ | ------ | ------------------------------------------------ |
| `bom.all_in_stock`                    | PASS               | PASS   | 5/5 chosen offers cover qty 5 and MOQ            |
| `bom.cost_under_budget`               | PASS               | PASS   | 3700 ¢ extended / 740 ¢ per unit                 |
| `bom.lead_time_under_days`            | PASS               | PASS   | max 7 d ≤ 14 d default cap                       |
| `erc.assertions`                      | PASS               | PASS   | the single assertion is `pass`                   |
| `erc.no_unconnected`                  | PASS               | FAIL   | `net:SWDIO` has one MCU pin — see deviations     |
| `layout.testpads.min_count`           | PASS               | PASS   | 8 pads ≥ 8                                       |
| `layout.testpads.nets_covered`        | SKIP               | SKIP   | `/keyboard` absent                               |
| `fw.matrix_pins_match_ir`             | SKIP               | FAIL   | no `/keyboard` node; plugin returns FAIL, not SKIP |
| `fw.qmk_compile`                      | SKIP               | FAIL   | QMK present, then no `/keyboard` → FAIL          |
| `fw.matrix_scan`                      | SKIP               | SKIP   | declared-not-implemented, always SKIP            |
| `fw.renode_boot`                      | SKIP               | SKIP   | `STM32G0B1CBT6` outside the STM32F411 platform   |
| `fab.quote_under_budget`              | SKIP               | SKIP   | no quotes fetched                                |
| `mech.plate_switch_cutouts_14mm`      | SKIP               | SKIP   | no switch references found                       |
| `mech.case_usb_cutout_aligned`        | SKIP               | SKIP   | no switch references found                       |
| `mech.pogo_spacing_ge_2p54`           | SKIP               | SKIP   | no switch references found                       |
| `mech.jig_no_collision`               | SKIP               | SKIP   | no switch references found                       |
| `mech.enclosure_clearance`            | SKIP               | SKIP   | no switch references found                       |

No `ERROR` was observed where a `SKIP` was expected. Two gates `FAIL` where the brief
implied `SKIP`/`PASS`; both are reported above and below.

## Design decisions

- **Domain-generic fixture.** The IR contains no keyboard/mech/fab/orders/sim/gates
  nodes, so every keyboard- and CAD-specific gate must SKIP from absent data. The CAD
  gates SKIP with the same field (`/keyboard/keys: no switch references found`) because
  `derive_models()` raises on the first missing model, exactly as designed for a
  non-keyboard board.
- **Synthetic sourcing.** All offers are `vendor: "other"` with `https://example.com/...`
  URLs and integer minor-unit prices matching the brief ($2.80 / $1.20 / $2.50 / $0.50 /
  $0.40 → 740 ¢/unit, 3700 ¢ at qty 5), comfortably inside the 1500/7500 ¢ budget.
- **Test-only timestamps.** All timestamps are `2026-11-06T00:00:00Z` (the work date).
- **No invented LCSC codes / datasheet values** — manufacturers and simplified seed pin
  numbers only.

## Deviations from contract (should be none)

- **No contract deviations.** The example validates through both parsers and the
  round-trip/patch contract tests remain green (32 passed). No root files were touched.

## Brief inconsistencies / open issues (reported, not fixed)

1. **`erc.no_unconnected` FAILs on `net:SWDIO`.** The brief fixes the net list to seven
   nets and states "all nets ≥2 pins", but also requires an eighth test pad "on U1 SWDIO —
   label it". `TestPad.net_ref` is required and must resolve, so SWDIO must be a declared
   net; with the frozen component list only U1 carries SWDIO, so the net has a single
   electrical pin. The pure ERC gate counts component pins (not test pads) and therefore
   reports `1 net(s) have fewer than 2 connected pins` (`net:SWDIO`). The other seven nets
   each connect ≥2 pins. I kept the SWDIO pad and recorded the honest FAIL rather than
   dropping an explicit layout requirement. If a passing ERC is required, the brief needs
   either a second SWDIO connection (e.g. a debug header) or the gate should treat test
   pads as connections.
2. **`fw.matrix_pins_match_ir` returns FAIL, not SKIP, without `/keyboard`.** The qmk
   plugin's `matrix_pins_gate` explicitly FAILs when the IR has no `/keyboard` node. The
   brief said "all `fw.*` gates SKIP honestly". This is plugin behaviour (not owned by
   WP-6.2) — a non-keyboard fixture cannot make it SKIP. `fw.renode_boot` and
   `fw.matrix_scan` do SKIP correctly.
3. **`fw.qmk_compile` is host-dependent.** It SKIPs only when the QMK CLI/`QMK_HOME` is
   unavailable (the sanitized-environment behaviour WP-4.5 relies on). On a machine with
   QMK installed it proceeds and FAILs on the missing `/keyboard` node. This run recorded
   the FAIL because QMK was present.
4. **Known daemon issue (pre-existing, WP-4.5 #1).** The `erc.no_unconnected` FAIL result
   carries pin-scoped refs (`comp:U1.5`), which `IRStore` ref-integrity rejects when
   persisting to `/gates/results`; the full result is still returned by `gates.run`.

## Root changes needed (orchestrator-owned)

None.
