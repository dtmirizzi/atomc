# WP-4.2 `plugin-renode` — handoff

Branch `wp/4.2-plugin-renode` · package `plugins/plugin-renode/**` · tests
`plugins/plugin-renode/python/tests/**` · docs `plugins/plugin-renode/docs/hil-checklist.md` and
`plugins/plugin-renode/README.md`.

## What was built

A Python Renode plugin (`atomc_plugin_renode`) that derives platform/run scripts from the IR and
runs emulation gates that never overstate what Renode proves. All brief deliverables:

1. **Package + manifest** — `plugins/plugin-renode/python` (hatchling, `src/` layout, `py.typed`)
   with entry point `renode = atomc_plugin_renode:plugin`. Manifest mirrored in
   `plugins/plugin-renode/atomc-plugin.json` and in `manifest_data.py` (a test asserts parity):
   watch `renode:generate` (`/firmware` + `/simulation`), `produces ["/simulation"]`,
   gates `gate:fw.renode_boot` / `gate:fw.matrix_scan`, tool `renode_generate`.
2. **Pure IR → script derivation** (`derive.py`) — `.repl` that `using`s Renode's generic
   `platforms/cpus/stm32f4.repl` and enumerates the matrix GPIO ports and IR peripheral map as
   `//` comments, plus a `.resc` that loads the `kind: "elf"` artifact from
   `/firmware/targets/*/artifacts` and `start`s. Byte-deterministic for identical
   IR + `repl_path`/`elf_path`/`timeout_s`. Goldens committed under `tests/goldens/`.
3. **`gate:fw.renode_boot`** (`plugin.py` + `runner.py` + `analysis.py`) — headless Renode through
   an injectable `RenodeRunner`; `SKIP` when the binary / MCU / ELF is unavailable; `PASS` only when
   a configured banner (`ext.renode.boot_markers`, default `QMK`/`atomc`) appears with no Cortex-M
   fault; `FAIL` on HardFault, timeout without banner, non-zero exit, or bannerless completion, with
   bounded (6000-char) log evidence. USB HID is never mentioned.
4. **`gate:fw.matrix_scan`** — always `SKIP` with the HIL reason; no fabricated scan.
5. **Recorded-HIL checklist** — `plugins/plugin-renode/docs/hil-checklist.md`.
6. **Tests** — 48 deterministic pytest cases (derivation goldens, determinism, classification,
   runner binary resolution/command shape/timeout, gates, tool, manifest parity, SDK conformance,
   daemon project-tree loading). No Renode install required.
7. **README** documenting surface, tool-name deviation, repl comment syntax and boot markers.

Real smoke (not a test): with Renode 1.17.0 at `~/.local/bin/renode`, the generated `.repl` plus
`.resc` loaded a compiled Cortex-M ELF, printed `Machine started` and ran to the timeout with no
HardFault. This surfaced and fixed a real bug — `.repl` comments must be `//`, not `#`.

## How to verify (exact commands)

```bash
uv run pytest plugins/plugin-renode/python -q
uv run ruff check plugins/plugin-renode/python
uv run ruff format --check plugins/plugin-renode/python
uv run mypy plugins/plugin-renode/python/src

# coverage (70% floor for plugins)
uv run pytest plugins/plugin-renode/python -q --cov=atomc_plugin_renode --cov-report=term-missing
```

Observed at handoff: **48 passed**; `atomc_plugin_renode` coverage **96 %**; ruff check/format and
mypy `--strict` clean. Optional real-Renode smoke, on a host with Renode installed:

```bash
ATOMC_RENODE_BIN=~/.local/bin/renode uv run pytest plugins/plugin-renode/python -q
```

(`find_renode_binary` honours `ATOMC_RENODE_BIN`, then `PYRENODE_PATH`, then `PATH`, then the macOS
portable/app locations.)

## Design decisions

- **`using` the shipped STM32F4 platform instead of hand-writing peripherals.** Renode 1.17.0 has
  no STM32F411 platform file; its generic `stm32f4.repl` defines the GPIO/USART/NVIC set QMK needs.
  The generated `.repl` documents the IR-derived pins/addresses rather than redeclaring (and
  conflicting with) Renode's own definitions. IR memory sizes are printed as comments; the model's
  flash/RAM differ, which is called out as informational, not a claim.
- **Timeout lives in the runner, not the script.** Renode 1.17.0 has no `--console`; the headless
  invocation is `renode --disable-gui --plain --port -1 <script>`. `emulation RunFor` proved
  unreliable in scripted headless mode, so the `.resc` ends at `start` and the subprocess timeout
  bounds the run. A banner found before the kill still yields `PASS`.
- **`SKIP` is the default for anything unproven.** Missing binary, MCU outside `STM32F411*`, missing
  ELF, or an unimplemented gate all `SKIP` with text evidence; the boot gate never fabricates a
  `PASS`.
- **Manifest structured for both SDK and daemon.** `atomc_plugin.json` is the project-tree
  discovery contract; the same data is validated at import by `@atomc_plugin`, and a test asserts
  the file and code do not drift.
- **Tool name is `renode_generate`.** See deviations.

## Deviations from contract

- **Tool name `renode_generate`, not `renode.generate`.** The frozen manifest schema restricts tool
  names to `^[a-z0-9]+(?:[_-][a-z0-9]+)*$`; a dot is invalid. The brief's `renode.generate` cannot
  validate. No semantic change.
- **Gate ids carry the `gate:` prefix** (`gate:fw.renode_boot`, `gate:fw.matrix_scan`) as required
  by the manifest contract. The stored IR keys (after the daemon strips the prefix) are
  `fw.renode_boot` / `fw.matrix_scan`, matching PLAN §1.2.
- **`renode --console` is not a Renode 1.17.0 flag.** Used `--disable-gui --plain --port -1`
  instead (same intent: headless console).
- **`.repl` comments use `//`.** `#` lines make Renode hang while loading the platform — found via
  the real smoke and now covered by tests.
- **`_PluginManifest` subclass** omits unset optional fields on `model_dump`. Workaround for a
  WP-2.2 SDK defect (below); not a contract change.

## Open issues

- **WP-2.2 SDK: `conformance()` rejects python-only runtime.** `conformance()` re-validates
  `manifest.model_dump(mode="json")`, which emits `"ts": null` for an unset `runtime.ts`; the shared
  schema allows only absent or a string, so every python-only plugin fails conformance. `plugin.py`
  works around it with a `PluginManifest` subclass that dumps with `exclude_none=True`. Remove the
  subclass once the SDK dumps absent optionals. (Reported here; SDK is not owned by this WP.)
- **WP-2.3 daemon: entry-point discovery cannot ingest SDK manifest models.**
  `atomcd.plugins.discovery._resolve_entry` calls `Manifest.model_validate(sdk_plugin_manifest)`,
  which pydantic rejects with `Input should be a valid dictionary or instance of Manifest`. This
  breaks `discover_from_entry_points()` for the SDK plugin (reproduced locally). Project-tree
  discovery (`load_plugin` over `atomc-plugin.json`) works and is tested. Needs a daemon-side
  `model_dump()` coercion — affects every SDK-decorated plugin, not just this one.
- **The tool only writes `/simulation` when the node already exists.** `ctx.ir_transact` plus the
  `produces` scope cannot create a missing top-level node (the daemon's `map_upsert` is not exposed
  to plugins). The example IR always has `/simulation`; a missing node is logged as
  `recorded_in_ir: false` rather than crashing.
- **Relative IR paths require discovering the project root.** `_generate` walks up from
  `artifact_root` to the directory containing `system_ir.json`; if not found it records the path
  relative to the artifact root. The host protocol does not expose `project_root`.
- **Default boot markers may not match QMK.** A stock QMK build may print nothing; the gate then
  `FAIL`s (never a false `PASS`). Set `ext.renode.boot_markers` to the real banner, or accept that
  the gate is a strict assertion.

## Root changes needed (orchestrator-owned)

- **`uv.lock` regeneration.** `plugins/*/python` is already a workspace member glob, so no
  `pyproject.toml` edit is needed, but the new `atomc-plugin-renode` distribution must enter
  `uv.lock`. It is intentionally **not** committed here (lockfile is orchestrator-owned). CI's
  `uv sync --all-packages` (not `--frozen`) regenerates it; run `uv sync --all-packages` on the
  merge worktree.
- **Daemon `_resolve_entry` fix** (open issue above) for entry-point plugin discovery.
- **SDK `conformance` fix** (open issue above) for python-only plugins.
