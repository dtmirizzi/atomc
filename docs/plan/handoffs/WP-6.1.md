# WP-6.1 `example-drivetrain` — handoff

Branch: `wp/6.1-example-drivetrain` · Status: done (with recorded plugin deviations)

## What was built

A non-keyboard atomc fixture, `examples/atomc-drivetrain`, modeled on the
openinverter.org architecture for a reused Tesla-style drive-unit power stage. It
proves the system IR is domain-generic: the optional `/keyboard` node is absent and
all keyboard-specific gates skip or (see below) fail honestly against the absent
data.

- `examples/atomc-drivetrain/system_ir.json` — 17 components, 20 nets, two `pass`
  assertions, a baremetal `fw:openinverter` STM32F407VGT6 target, a 120×80 mm
  4-layer layout with 12 pogo test pads and 4 mounting holes, a tray enclosure with
  no plate/jig, 17 BOM lines, and a 4-layer ENIG fabrication spec with no quotes.
  No `/keyboard`, `/orders`, `/simulation` or `/gates` node.
- `examples/atomc-drivetrain/atomc.config.ts` — budget gate at 12000¢/unit /
  24000¢ total, qty 2, and the plugin list.
- `examples/atomc-drivetrain/README.md` — modeled-fixture + HV safety disclaimer,
  openinverter attribution, component table, full expected gate-outcome table, and
  runnable verification commands.
- `tests/contract/ts/roundtrip.test.ts` — `"atomc-drivetrain"` added to `EXAMPLES`.
- `tests/contract/ts/fixtures.test.ts` — the example dir added to `VALID_DIRS`.
- `docs/examples/atomc-drivetrain.md` + `docs/examples/index.md` — walkthrough page
  and examples-index entry.

## How to verify (exact commands)

From the repository root:

```bash
uv sync --all-packages
uv run python -c "from atomc_core_ir import SystemIR; SystemIR.load('examples/atomc-drivetrain/system_ir.json')"

pnpm install --frozen-lockfile
pnpm --filter @atomc/core-ir build          # dist needed by the contract package
pnpm --filter @atomc/contract-tests test    # 33 passed
pnpm --filter @atomc/contract-tests typecheck
pnpm exec biome check tests/contract/ts examples/atomc-drivetrain/atomc.config.ts
```

Gate outcomes via the daemon's real `GateRunner` (does not mutate the committed
file — it runs on a temp copy):

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
    store = IRStore(tmp); store.load(); events = EventBus()
    registry = build_registry(tmp, store=store, events=events)
    for r in sorted(await GateRunner(registry=registry, store=store, events=events).run(),
                    key=lambda x: x["id"]):
        print(f"{r['id']}\t{r['status']}\t{r['summary']}")
asyncio.run(main())
PY
```

Real daemon E2E (used for the table below) was run with a temp project copy and a
private `--state-dir`/`--port`, driving `dag.run`/`dag.status`/`gates.list`/`gates.run`
over the authenticated WebSocket RPC.

## Gate results (expected-vs-actual, real daemon)

`gates.run` (every declared gate) and `gates.list` after a **fresh** `dag.run`:

| Gate | `gates.run` | after fresh `dag.run` | Notes |
| --- | --- | --- | --- |
| `gate:erc.no_unconnected` | PASS | PASS | 20 nets, all ≥ 2 pins |
| `gate:erc.assertions` | PASS | PASS | 2 `pass` assertions |
| `gate:layout.testpads.min_count` | PASS | PASS | 12 ≥ 8 |
| `gate:layout.testpads.nets_covered` | SKIP | SKIP | no `/keyboard` |
| `gate:bom.all_in_stock` | PASS | **not reached** | DAG aborts before this node |
| `gate:bom.cost_under_budget` | PASS | **not reached** | 9940¢ extended, 4970¢/unit |
| `gate:bom.lead_time_under_days` | PASS | **not reached** | max 7 ≤ 14-day cap |
| `gate:fab.quote_under_budget` | SKIP | SKIP | `quotes: []` |
| `gate:mech.plate_switch_cutouts_14mm` | SKIP | SKIP | "no switch references found" |
| `gate:mech.case_usb_cutout_aligned` | SKIP | SKIP | same derivation error |
| `gate:mech.pogo_spacing_ge_2p54` | SKIP | SKIP | same derivation error |
| `gate:mech.jig_no_collision` | SKIP | SKIP | same derivation error |
| `gate:mech.enclosure_clearance` | SKIP | SKIP | same derivation error |
| `gate:fw.renode_boot` | SKIP | **not reached** | STM32F407VGT6 not in generated `stm32f4.repl` (`STMicroelectronics.STM32F411` only) |
| `gate:fw.matrix_scan` | SKIP | **not reached** | declared-not-implemented |
| `gate:fw.matrix_pins_match_ir` | FAIL | FAIL | plugin FAILs on absent `/keyboard` |
| `gate:fw.qmk_compile` | FAIL | FAIL | toolchain present, then FAILs on absent `/keyboard` |

Every SKIP traces to absent data (`/keyboard`, no quotes, no switches, unsupported
MCU) and every PASS traces to recorded IR data. No `PASS` is bare; each carries
evidence.

## Deviations from contract / brief

1. **`fw.*` gates were expected to SKIP but two FAIL.** The brief stated all `fw.*`
   gates should SKIP for this fixture. Actual plugin behaviour:
   - `gate:fw.matrix_pins_match_ir` (**FAIL**) has no toolchain guard and returns
     FAIL when `/keyboard` is absent (`plugins/plugin-qmk/.../gates.py`, `matrix_pins_gate`).
   - `gate:fw.qmk_compile` returns SKIP only when the QMK toolchain is missing; with
     QMK installed it FAILs on absent `/keyboard`.
   Per the brief ("do not edit the plugin"), this is recorded, not patched.
2. **`renode:generate` watch raises and aborts a fresh full DAG run.** The
   `renode:generate` node handler raises `DerivationError: no ELF firmware artifact
   in /firmware`; `DagScheduler._execute` re-raises and stops the topological walk,
   so a fresh `dag.run` never reaches the `bom.*`, `fw.renode_*`, `fw.matrix_scan`,
   `orders.*` or `atopile` watch descendants. A direct `gates.run` still exercises
   the real `GateRunner` over the same IR and produced the full table above. This is
   a plugin/daemon robustness gap, not a fixture defect; the fixture intentionally
   has `artifacts: []` per the brief.
3. **LCSC codes omitted.** Every BOM line leaves `lcsc: null` because no LCSC code
   was verifiable from the brief; no codes were invented. The brief allows this.
4. **`/electrical/source`** is set to `{"kind": "atopile", "entry": "main.ato:App"}`
   because the frozen model requires a `source`; no `.ato` project exists (the IR is
   hand-authored). This mirrors the committed keyboard fixtures.

No contract changes; `docs/architecture/contracts/ir-schema.md` was read-only.

## Open issues

- The two QMK gate FAILs and the `renode:generate` DAG abort above are candidate
  fixes for `plugin-qmk` and `plugin-renode`/`atomcd` (skip on absent `/keyboard`;
  make the generate watch non-fatal or gate on artifact presence). They are outside
  this WP's ownership.
- `uv run pytest -q`: 713 passed, 1 failed, 3 skipped, 1 xfailed. The single failure
  is `packages/daemon/python/tests/test_cli.py::test_status_with_stale_pid`, caused
  by an unrelated daemon already listening on `127.0.0.1:7437` in this environment
  (its `/health` answers, so the CLI reports `running: true`). It is unrelated to
  this fixture and pre-existing; it should pass on a clean machine with no daemon on
  7437.
- The example ships no `ato`/QMK source; it is an IR + daemon fixture only.

## Root changes needed

None. No root files, plugins, packages or other examples were edited.

## Commits

- `test(contract): round-trip atomc-drivetrain example`
- `feat(examples): add atomc-drivetrain control-board fixture`
- `docs(examples): walk through atomc-drivetrain`
