# WP-4.5 `e2e-vertical-slice` — handoff

Branch `wp/4.5-e2e-vertical-slice` · new package `tests/e2e` · no changes outside owned paths.

## What was built

A real-process end-to-end vertical slice for `atomc build` on `examples/atomc-pad`. The suite
spawns the actual `atomcd serve` process with `uv run`, lets the daemon discover the four
built-in plugins (`atopile`, `renode`, `cad-jig`, `qmk`) through their `atomc.plugins` entry
points, derives the 18-node reactive DAG, runs every watch and gate, and reads the outcomes
back over the real WebSocket JSON-RPC transport via `@atomc/daemon-client`.

1. **`tests/e2e/ts/harness.ts`** — throwaway project/state/home/empty-PATH trees seeded from
   `examples/atomc-pad/system_ir.json`; real `atomcd serve` spawn; `/health` + `daemon.json`
   wait; token-redacted bounded logs; `runFullDag()` (subscribe-before-run, waits for every
   `dag.node.end` for the run id) and `waitForDagEnd()`; `finally`-safe stop plus an explicit
   process-death assertion. Mirrors the WP-2.6/WP-3.10 spawn pattern, adapted for entry-point
   plugin discovery (no fake plugin, no project-tree manifest).
2. **`tests/e2e/ts/vertical-slice.e2e.test.ts`** (5 tests) — all four plugins load with no
   error; the derived DAG contains exactly the 5 watch + 13 gate nodes; every node finishes
   `ok`; every gate outcome is asserted against the fixture's real status; the IR is unchanged
   on `/electrical`, `/keyboard`, `/layout`, `/firmware`, `/mechanical` while `/simulation` is
   mutated by the renode watch's real node handler.
3. **`tests/e2e/ts/failure-honesty.e2e.test.ts`** (2 tests) — transacts a new single-pin net
   (`net:ORPHAN` + `comp:J9`) over real RPC and asserts `erc.no_unconnected` returns `FAIL`
   whose evidence names the mutation; then adds a debug header (`comp:J8`) that connects the
   six dangling nets and asserts the gate flips to `PASS` with empty `unconnected` evidence.
4. **`tests/e2e/README.md`** — layer description, expected outcome table, sanitized-environment
   rationale, run instructions.
5. **`tests/e2e/{package.json,tsconfig.json,vitest.config.ts}`** — mirrors `tests/swarm`.

Determinism: ephemeral loopback port per daemon; one daemon per test; teardown removes the
temp tree and asserts the process is dead; `fileParallelism: false`; no vendor keys, LLM,
network beyond loopback, or hardware. Verified green twice consecutively.

## How to verify (exact commands)

The package is not yet in `pnpm-workspace.yaml` (root file — see "Root changes needed"), so
until the orchestrator wires it, build deps and run Vitest directly:

```bash
pnpm --filter @atomc/daemon-client build
pnpm --filter @atomc/core-ir build

cd tests/e2e
./node_modules/.bin/vitest run --reporter=verbose   # 7 passed
```

After the workspace entry + lockfile regeneration:

```bash
pnpm --filter @atomc/e2e-vertical-slice test        # 7 passed, twice in a row
pnpm --filter @atomc/e2e-vertical-slice typecheck    # tsc --noEmit clean
pnpm --filter @atomc/e2e-vertical-slice lint         # biome clean
```

Observed here (Node 25, macOS arm64): 7/7 passed on two consecutive runs, ~5 s per run after
the initial `uv` sync; `tsc --noEmit` and `biome check tests/e2e` clean.

## Design decisions

- **Entry-point discovery, not project-tree manifests.** The four plugins are installed
  workspace members exposing `atomc.plugins` entry points; the seed contains no
  `atomc-plugin.json`, so the test proves the daemon's entry-point path (whose
  `_resolve_entry` BaseModel coercion landed after WP-4.1/4.2 raised it).
- **Sanitized no-toolchain environment.** The daemon is spawned with `PATH` = an empty temp
  dir, `HOME` = a temp dir, `QMK_HOME` = a non-existent path, and
  `ATOMC_RENODE_BIN`/`PYRENODE_PATH` unset, with `UV_CACHE_DIR`/`UV_PYTHON_INSTALL_DIR`/
  `UV_TOOL_DIR` pinned to the real locations. This makes `fw.qmk_compile` and
  `fw.renode_boot` deterministically `SKIP` on both a clean CI runner and a developer machine
  that has Renode/QMK installed. Without it the suite would be host-dependent.
- **Outcomes come from `gate.result` events, not `gates.list`.** See open issue #1: the
  `erc.no_unconnected` FAIL result is rejected by IR ref-integrity when persisted. The
  `gate.result` event and the `gates.run` RPC return still carry the full authoritative
  result, so every assertion traces to a real daemon gate result over RPC.
- **IR-stability assertion scoped to non-produced nodes.** Watches without a handler are
  pure invalidation nodes and write nothing; `renode:generate` has a real handler and records
  script paths under `/simulation`. The test asserts `/simulation` changes and that
  everything a plugin does not produce is byte-identical.

## Deviations from contract (should be none)

- **No contract deviations.** The e2e layer only reads RPC results and mutates IR through the
  documented `ir.transact`.
- **Fixture-vs-brief note (not a contract deviation):** the brief anticipated the pad fixture
  would yield `PASS`/`SKIP` for the pure gates. In fact `gate:erc.no_unconnected` genuinely
  `FAIL`s on the committed `examples/atomc-pad/system_ir.json`: `SWDIO`, `SWCLK`, `NRST`,
  `BOOT0`, `UART_TX`, `UART_RX` each have a single MCU pin and no second component. Per the
  brief's "PASS/FAIL as the fixture data dictates" rule, the test records the real `FAIL` and
  its exact evidence instead of engineering a clean board. This matches WP-4.1's finding that
  the seeded pad board has single-pad nets.

## Open issues

1. **Daemon silently drops a gate FAIL whose `refs` are not IR ids.** `atopile`'s
   `erc.no_unconnected` returns refs like `comp:U1.5` (pin-scoped). `IRStore.map_upsert`
   validates refs and raises `RefIntegrityError` (a `ValueError`), which
   `GateRunner._persist` swallows, so the result never reaches `/gates/results` and
   `gates.list` omits it. Fix options: have the plugin emit only IR ids (`comp:U1`) in
   `refs`, or have the daemon strip/normalise unknown refs before persisting. Reported here;
   neither daemon nor plugin is owned by this WP.
2. **`fw.renode_boot` runs Renode even when the referenced ELF file does not exist.** The
   plugin checks that an ELF *path* is present in `/firmware` but not that the file exists,
   so on a host with Renode it launches emulation against a missing file and `FAIL`s on
   timeout. Not exercised by this suite (the sanitized env forces `SKIP`), but it is a latent
   host-dependent behaviour. Reported; plugin-renode is not owned here.

## Root changes needed (orchestrator-owned)

1. **Add the workspace entry** in `pnpm-workspace.yaml`:

   ```yaml
   - "tests/e2e"
   ```

   and run `pnpm install` to regenerate `pnpm-lock.yaml` (include `tests/e2e`'s deps:
   `@atomc/daemon-client`, `@types/node`, `@types/ws`, `typescript`, `vite`, `vitest`, `ws`).
2. **Turbo/CI wiring.** Register `tests/e2e` (`@atomc/e2e-vertical-slice`) with `test`,
   `typecheck`, `lint` scripts (already defined). Because every run spawns Python via `uv`,
   give it a **separate CI job** rather than folding it into the TS unit-test job; the job must
   run after `uv sync --all-packages` and after a TS build of `@atomc/daemon-client` and
   `@atomc/core-ir`. Suggested job commands and estimated runtime:

   ```bash
   uv sync --all-packages
   pnpm install --frozen-lockfile
   pnpm --filter @atomc/daemon-client build
   pnpm --filter @atomc/core-ir build
   pnpm --filter @atomc/e2e-vertical-slice test
   ```

   Observed runtime: ~5 s of test time plus one-time `uv` sync; budget a 10-minute job.
   The sanitized environment means no Renode/QMK installation is required in CI.
