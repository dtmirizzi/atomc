# WP-4.1 `plugin-atopile` — handoff

Branch `wp/4.1-plugin-atopile` · package `plugins/plugin-atopile/python` · manifest
`plugins/plugin-atopile/atomc-plugin.json`.

## What was built

The first Phase-4 hardware plugin: it compiles atopile projects through the `ato` CLI, imports
KiCad boards, and verifies the result with four pure IR gates.

1. **Python package** (`plugins/plugin-atopile/python`, hatchling `src/` layout,
   `atomc.plugins` entry point `atomc_plugin_atopile:plugin`) plus the shared
   `atomc-plugin.json` manifest. Declares gates `gate:erc.no_unconnected`,
   `gate:erc.assertions`, `gate:layout.testpads.min_count`,
   `gate:layout.testpads.nets_covered`; tools `compile` / `import_pcb` (fully qualified
   `atopile.compile` / `atopile.import_pcb`); one watch `atopile:build`; produces
   `/electrical` + `/layout`.
2. **`atopile.compile`** (`plugin.py` + `runner.py` + `electrical.py`): runs `ato build` via an
   injectable subprocess runner in the project directory. Missing `ato` → structured
   `UNAVAILABLE` (`available: false`); non-zero exit/timeout → `FAIL` with bounded stderr;
   success → `PASS` and writes components (from `build/builds/<target>/<target>.bom.json`), nets
   + pins (from the generated `.kicad_pcb`), and assertions (from the `.variables.ato.json`
   specs) to `/electrical` through the plugin context. atopile internals are never imported.
3. **`atopile.import_pcb`** (`pcb.py`): parses a `.kicad_pcb` with `kiutils` (lazy import; absent
   → `UNAVAILABLE`) into outline, placements and bottom-side test pads, writing `/layout`.
   Deterministic parse tests use a committed minimal fixture.
4. **Gates** (`gates.py`): pure checks over IR data — no subprocess/filesystem/network.
   `erc.no_unconnected` (no net with <2 pins), `erc.assertions` (fail→FAIL, unknown→SKIP),
   `layout.testpads.min_count` (`MIN_TEST_PADS = 8`), `layout.testpads.nets_covered` (matrix nets
   resolved from `/keyboard` keys + component pins, missing→FAIL).
5. **Tests**: 42 deterministic pytest cases — fake subprocess runner (PASS/FAIL/timeout),
   fake/real board loader, BOM/variables fixtures, all gates PASS/FAIL/SKIP, manifest + SDK
   conformance + daemon discovery, and referential-integrity filtering on layout writes.
6. **This handoff** plus `README.md` documenting the toolchain-optional design.

## How to verify (exact commands)

```bash
# plugin suite (without atopile/kiutils: 40 passed, 2 skipped)
uv run pytest plugins/plugin-atopile/python -q

# plugin suite with kiutils installed (42 passed)
uv pip install "kiutils>=1.4.8"
uv run pytest plugins/plugin-atopile/python -q

# lint / types (CI scopes)
uv run ruff check plugins/plugin-atopile/python
uv run ruff format --check --exclude '*.md' plugins/plugin-atopile/python
uv run mypy plugins/plugin-atopile/python/src

# whole Python workspace must stay green (daemon discovers this plugin's DAG)
uv sync --all-packages
uv run pytest -q            # 390 passed, 1 opt-in skip
```

Real-path exercise performed once on a copy of `examples/atomc-pad` with the installed
`ato 0.15.9` and `kiutils 1.4.8`:

- `compile` → PASS, 46 components, 68 nets, 6 assertions, no warnings.
- `import_pcb` → PASS, 46 placements, 15 test pads, outline from footprint bounds (see below).
- `erc.no_unconnected` → FAIL, 36 nets with fewer than 2 pins (the seeded board genuinely has
  single-pad nets); `layout.testpads.min_count` → PASS (15 ≥ 8).

## Design decisions

- **Subprocess, not internals.** `atomcd.kernels.atopile` reports `build` as unsupported; the
  plugin shells out and records the exit code as the source of truth. Tests inject a fake runner.
- **Merged writes.** `/electrical` and `/layout` have inbound references from
  firmware/sourcing/mechanical/keyboard. The plugin unions its output with existing entries and
  drops placement/test-pad references that would dangle, so a write never breaks the document.
- **`kiutils` is an optional extra** (`atomc-plugin-atopile[pcb]`); tests skip the two real
  parser cases when it is missing, matching the daemon's lazy-kernel pattern.
- **One watch node** `atopile:build` with `ir: ["/electrical", "/layout"]`. See Deviations.
- **Gate outcomes are honest:** assertions with `unknown` status SKIP rather than PASS; a net
  with zero or one pin FAILs; a missing `/electrical`/`/layout`/`/keyboard` SKIPs.

## Deviations from contract (should be none)

- **Manifest watches:** the brief said "watches `/electrical` + `/layout`". Two separate watch
  nodes (`atopile:compile` watching `/electrical`, `atopile:layout` watching `/layout`) are
  impossible with the daemon's DAG derivation: `produces` scopes are plugin-global, so each
  watch would see the other's produced pointer and form a cycle, breaking
  `DagScheduler.build()` (reproduced: daemon `test_cli.py` failed). The plugin therefore declares
  a single `atopile:build` watch with both IR pointers and both files globs, which is acyclic.
  All four gates `after` it.
- No other contract deviations. The manifest passes both the Python SDK (raw + conformance via a
  round-trip-safe subclass) and the daemon's own manifest model.

## Open issues

- **No Edge.Cuts in the seeded boards.** `examples/atomc-pad` and `atomc-keeb` `.kicad_pcb`
  files have no Edge.Cuts geometry, and their net names are anonymous (`hv`, `1-5`). `import_pcb`
  falls back to a footprint-bounds rectangle (recorded as a `warnings` entry) and `compile`
  extracts the board's actual net names. A future WP-1.6/4.5 pass should align the example board
  designators/nets with the hand-authored `system_ir.json`.
- **Example designators differ from the IR** (`U3` on the board vs `comp:U1` in
  `system_ir.json`), so a real `compile` against `examples/atomc-pad` merges rather than
  reconciles. The merge keeps cross-node references valid; full reconciliation is downstream work.
- **`erc.no_unconnected` on the seeded pad example FAILs** (36 single-pad nets) — expected for
  that fixture, not a plugin bug.

## Root changes needed

- **`uv.lock`** is stale after adding the `plugins/plugin-atopile/python` workspace member; the
  orchestrator should run `uv sync --all-packages` and commit the regenerated lock (left
  untouched here per the ownership rules).
- **WP-2.2 (SDK) fix recommended:** `conformance()` re-validates a parsed manifest via
  `model_dump(mode="json")`, which emits `"ts": null` for Python-only runtimes; the shared schema
  rejects null, so *any* Python-only manifest fails conformance. Dump with `exclude_none=True`
  (as this plugin works around with `ConformantManifest`).
- **WP-2.3 (daemon) fix recommended:** `discover` / `_resolve_entry` calls
  `Manifest.model_validate(sdk_plugin_manifest)` directly, which pydantic rejects for a foreign
  `BaseModel`; coerce with `model_dump()` first (as `validate_manifest` already does). This
  plugin exposes a plain `.manifest` dict to work around it.
