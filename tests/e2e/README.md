# `tests/e2e` — `atomc build` vertical slice (WP-4.5)

This package is the milestone end-to-end test for the hardware vertical slice. It spawns
the **real** `atomcd` process, lets it discover the four built-in plugins through their
installed `atomc.plugins` entry points, seeds a throwaway project from the committed
`examples/atomc-pad/system_ir.json`, runs the reactive DAG, and reads every gate outcome
back over the real WebSocket JSON-RPC transport.

Nothing is mocked: no fake plugin, no fixture daemon, no hand-authored gate results. The
only environmental control is a sanitized process environment (see below) that makes
external-toolchain behaviour deterministic.

## Layout

| Path                             | Responsibility                                                                                                                                                                                                                                                                     |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ts/harness.ts`                  | Temp project/state/home dirs seeded from `examples/atomc-pad`; real `atomcd serve` spawn via `uv run`; sanitized no-toolchain environment; `/health` wait; token-redacted bounded logs; `runFullDag`/`waitForDagEnd` helpers; `finally`-safe teardown and process-death assertion. |
| `ts/vertical-slice.e2e.test.ts`  | Plugin discovery, DAG derivation, full run over RPC, exact per-gate outcomes, IR-stability check (unchanged where no plugin writes; `/simulation` mutated by the renode watch).                                                                                                    |
| `ts/failure-honesty.e2e.test.ts` | Mutates the IR over real RPC (new single-pin net → `FAIL` naming it; debug header connecting the dangling nets → `PASS`), so both failure and recovery are shown to come from live daemon state.                                                                                   |

## Expected outcomes for the committed pad fixture

The harness runs the daemon with **no** `qmk`/`renode` on `PATH`, a temp `HOME`, and a
non-existent `QMK_HOME`, so toolchain-dependent gates always `SKIP`:

| Gate                                | Status | Why                                                             |
| ----------------------------------- | ------ | --------------------------------------------------------------- |
| `gate:erc.no_unconnected`           | FAIL   | 6 MCU-only nets have a single pin in the hand-authored IR       |
| `gate:erc.assertions`               | PASS   | one recorded assertion passes                                   |
| `gate:layout.testpads.min_count`    | PASS   | 15 test pads ≥ 8                                                |
| `gate:layout.testpads.nets_covered` | PASS   | all 6 matrix nets have a pad                                    |
| `gate:fw.matrix_pins_match_ir`      | PASS   | generated QMK matrix pins equal the IR pins                     |
| `gate:fw.qmk_compile`               | SKIP   | `qmk` not found on the sanitized `PATH`                         |
| `gate:fw.renode_boot`               | SKIP   | no Renode binary in the sanitized environment                   |
| `gate:fw.matrix_scan`               | SKIP   | declared-not-implemented; requires HIL, never a fabricated scan |
| five `gate:mech.*` gates            | PASS   | pure geometric checks over the pad IR                           |

`gate:erc.no_unconnected` genuinely fails on the committed fixture: `SWDIO`, `SWCLK`,
`NRST`, `BOOT0`, `UART_TX` and `UART_RX` each have a single MCU pin and no second component
in the IR. Recording the real `FAIL` — and its exact `unconnected` evidence — is the point;
a "clean" board would have to be engineered, not assumed.

## Why the environment is sanitized

Toolchain gates fall back to `SKIP` only when the binary is genuinely absent. Without a
sanitized environment the tests would pass on a CI runner with no toolchains but fail on a
developer machine that has Renode or QMK installed. The harness therefore spawns the daemon
with `PATH` pointing at an empty temp dir, `HOME` at a temp dir, `QMK_HOME` at a
non-existent path, and `ATOMC_RENODE_BIN`/`PYRENODE_PATH` unset, while pinning
`UV_CACHE_DIR`/`UV_PYTHON_INSTALL_DIR`/`UV_TOOL_DIR` at the real locations so `uv run`
reuses the already-synced workspace.

## How to run it

Until the orchestrator adds `tests/e2e` to `pnpm-workspace.yaml` (see the WP-4.5 handoff),
`pnpm --filter` cannot resolve the package. Build the workspace deps and run Vitest
directly:

```bash
pnpm --filter @atomc/daemon-client build
pnpm --filter @atomc/core-ir build

cd tests/e2e
./node_modules/.bin/vitest run --reporter=verbose
```

Once the workspace entry and lockfile are regenerated, the normal commands work:

```bash
pnpm --filter @atomc/e2e-vertical-slice test
pnpm --filter @atomc/e2e-vertical-slice typecheck
pnpm --filter @atomc/e2e-vertical-slice lint
```

The suite must also pass on a clean checkout with no external toolchains (the sanitized
environment guarantees the same `SKIP` paths); it needs Python 3.14 + `uv` and Node 22/25.

## Determinism

- Ephemeral loopback port per daemon; no fixed ports, no network beyond loopback.
- One daemon per test, torn down in `afterEach`; teardown asserts the process is dead and
  removes the temp tree.
- `fileParallelism: false` because each file spawns its own daemon over `uv`.
- No vendor keys, no LLM, no hardware.

## Known daemon-side issue surfaced by this layer

`gate:erc.no_unconnected`'s `FAIL` result cannot be persisted to `/gates/results`: the
atopile gate returns pin-scoped refs (`comp:U1.5`), which are not valid IR ids, and the IR
store's ref-integrity check rejects the write. The daemon catches that as a `ValueError` and
drops the result, so the outcome is only observable via the `gate.result` event (and the
`gates.run` RPC return). The E2E tests therefore read gate outcomes from events rather than
`gates.list`. See the handoff for the fix suggestion (daemon should either map or drop
non-IR refs before persisting).
