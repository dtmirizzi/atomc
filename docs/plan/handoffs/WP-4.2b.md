# WP-4.2b — plugin-qmk handoff

## What was built

`plugins/plugin-qmk/python` is a Python plugin package (`atomc-plugin-qmk`) registered through
the WP-2.2 plugin SDK. It derives QMK configuration from the canonical IR and exposes generation,
compile-gate and compile-tool handlers plus a source-tree `atomc-plugin.json` manifest.

* **IR → QMK derivation** (`derivation.py`):
  * `derive_keyboard_json()` builds a deterministic QMK `keyboard.json` from the `keyboard`
    matrix, USB identity, `qmk.keyboard_path`, bootloader/processor/board and the key layout
    geometry. Key units are converted to millimetres using the IR contract's 19.05 mm key unit.
  * `derive_keymap_c()` builds a single `LAYOUT(...)` base layer from `keycode_default`.
  * `derive()` returns both files plus their repo-relative paths under
    `keyboards/<keyboard_path>/`.
  * `materialize()` writes the derived files atomically with POSIX newlines.
* **Gates** (`gates.py`):
  * `qmk.derive` — generates QMK files into the plugin artifact directory and confirms the
    generated matrix pins match the IR.
  * `qmk.compile` — locates `qmk` on `PATH` and `QMK_HOME`, materialises the keyboard, invokes
    `qmk compile -kb … -km default`, captures bounded output, and records the compiled artifact
    (bin/hex/uf2/elf) into the `/firmware` IR node.
  * Missing toolchain is reported as `SKIP` with actionable suggestions rather than a fake pass.
  * A compile failure or IR write failure is reported as `FAIL` with bounded evidence.
* **Tools** (`gates.py`):
  * `qmk_generate` — derive QMK files without compiling.
  * `qmk_compile` — run the derivation + compile flow as a mutating tool.
* **Manifest** (`manifest.py` + `plugins/plugin-qmk/atomc-plugin.json`):
  * plugin name `qmk`, version `0.1.0`
  * watches `/keyboard`
  * produces `/firmware`
  * both gates and both tools registered with matching handler names.
* **Tests** (`plugins/plugin-qmk/python/tests`):
  * derivation golden tests against the `examples/atomc-pad/qmk` fixture, byte-for-byte.
  * matrix-pin gate tests.
  * compile-gate tests with a fake subprocess runner for PASS/FAIL/SKIP paths.
  * manifest conformance through the SDK's `assert_conformance()`.

## How to verify (exact commands)

```bash
uv sync --all-packages
uv run pytest plugins/plugin-qmk/python -q
uv run ruff check plugins/plugin-qmk
uv run ruff format --check plugins/plugin-qmk
uv run mypy plugins/plugin-qmk/python/src
```

Expected: 39 tests pass, Ruff and mypy are clean.

## Design decisions

* **Artifact recording type safety**: The JSON Patch `value` for appending an artifact to a target's
  `artifacts` array is a heterogeneous list (`[*kept, artifact]`). `kept` items are `Any` and
  `artifact` is a `dict[str, Any]`. To keep strict mypy happy without weakening the rest of the
  module, the list is materialised into a typed `value_list: list[Any]` variable before being
  inserted into the patch operation. This avoids a false positive where mypy inferred `list[str]`
  from the first branch's `value` assignment.
* **Compile gate honesty**: A missing `qmk` executable or `QMK_HOME` produces `SKIP`, not `FAIL`.
  This matches the daemon's gate semantics and avoids blocking users who only edit QMK sources.
* **Artifact freshness**: The compile gate only accepts artifacts whose `mtime` is newer than the
  compile start time. Stale `.build` outputs from a previous run are ignored and reported as a
  failure with evidence.
* **Symlink safety**: The gate refuses to overwrite an existing non-symlink keyboard directory in
  `QMK_HOME`; it only replaces symlinks it owns. This keeps the plugin from clobbering a real QMK
  tree.
* **Bounded output**: Compiler stderr/stdout is truncated to keep gate evidence and IR snapshots
  small and deterministic.

## Deviations from contract

None. The plugin follows the manifest contract, gate-result contract and IR schema v0.1 for the
`/firmware` artifact fields.

## Open issues

* None blocking. The plugin does not ship a TypeScript runtime; the manifest intentionally declares
  only the Python entrypoint (`runtime.ts` was dropped during conformance because the brief's
  TS-side deliverable belongs to a separate plugin package).
* The compile gate requires a real QMK installation for a live PASS; CI covers SKIP/FAIL and the
  derivation path with a fake runner. A real QMK run remains an opt-in integration check.

## Root changes needed

* `uv.lock` needs a workspace member entry for `plugins/plugin-qmk/python`. Running
  `uv sync --all-packages` updates it automatically; the orchestrator should commit the regenerated
  lockfile after merging this branch. The plugin package is already listed in
  `pyproject.toml`'s workspace glob (`plugins/*/python`), so no root manifest change is required.
