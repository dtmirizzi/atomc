# WP-4.3 `plugin-cad-jig` — handoff

Branch `wp/4.3-plugin-cad-jig` · package `plugins/plugin-cad-jig/python` ·
manifest `plugins/plugin-cad-jig/atomc-plugin.json`.

## What was built

A Python atomc plugin (`atomc-plugin-cad-jig`, hatchling, src layout, `atomc.plugins` entry
point `cad-jig = "atomc_plugin_cad_jig:plugin"`) with a validated manifest, five pure mechanical
gates and a `cad-jig:generate` tool. All brief deliverables:

1. **Validated manifest** (`atomc-plugin.json`, byte-identical at the plugin root and inside the
   package): watches `/mechanical` + `/layout`, produces `/mechanical`; five blocking
   `mech.*` gates owned by `mech-agent`; tool `generate` (mutating, `mech-agent`, targets
   `plate|case|jig|pcb`, formats `step|stl`); no CLI/UI.
2. **Pure parametric derivation** (`models.py`): plate cutout centers from IR switch placements
   and bounds from the outline; tray walls, base floor and a USB-C cutout on the edge nearest the
   IR connector placement; pogo receptacle positions from `/layout` test pads and alignment pins
   from mounting holes; PCB footprint projection (outline polygon, component bboxes, keepouts).
   All geometry math is plain arithmetic and golden-tested against the atomc-pad IR fixture.
3. **Five pure gates** (`gates.py`, no CAD import):
   * `gate:mech.plate_switch_cutouts_14mm` — 14 mm cutouts on the 19.05 mm grid, inside bounds;
   * `gate:mech.case_usb_cutout_aligned` — connector edge proximity + centred cutout + Z fit;
   * `gate:mech.pogo_spacing_ge_2p54` — all pairwise pogo distances ≥ 2.54 mm;
   * `gate:mech.jig_no_collision` — drill/pin circles vs component/keepout projections and board;
   * `gate:mech.enclosure_clearance` — walls/clearance minima, components inside the cavity.
   Gate handlers return frozen-GateResult fields (`status/summary/evidence/suggestions/refs`);
   the daemon runner fills metadata. Missing/contradictory IR returns an honest `SKIP`.
4. **`cad-jig:generate` tool**: lazily imports build123d and builds plate/case/jig/pcb solids,
   exporting STEP/STL into the plugin artifact directory and replacing `/mechanical/artifacts`
   with the new records (existing non-cad-jig artifacts preserved). Without build123d it returns
   `{status: "unavailable", reason: "build123d_missing", artifacts: []}` and writes nothing —
   never a fabricated STEP.
5. **Tests**: 32 passed, 1 xfailed (see SDK bug below) covering model goldens, all five gates on
   PASS and mutated-FAIL paths, derivation errors, handler SKIP paths, manifest sync/conformance,
   the unavailable tool path, and the artifact-recording path with a stubbed builder.
6. **This handoff.**

Layout: `src/atomc_plugin_cad_jig/{models,gates,cad,plugin,errors}.py`, `tests/` with an
atomc-pad IR fixture copy. Importing the package never imports build123d.

## How to verify (exact commands)

```bash
# workspace members must be installed first (CI does this)
uv sync --all-packages

uv run pytest plugins/plugin-cad-jig/python -q
# observed: 32 passed, 1 xfailed

uv run ruff check plugins/plugin-cad-jig
uv run ruff format --check plugins/plugin-cad-jig
uv run mypy plugins/plugin-cad-jig/python/src

# coverage (plugin total; cad.py is only partially traced without build123d)
uv run pytest plugins/plugin-cad-jig/python -q --cov=atomc_plugin_cad_jig --cov-report=term-missing
# observed: TOTAL 82 %

# full workspace suite (checks daemon plugin discovery too)
uv run pytest -q
# observed: 380 passed, 1 skipped (hardware opt-in), 1 xfailed
```

Optional CAD exercise: `build123d` is **not installed** in this worktree, so the solid builders
were not executed. To exercise them:

```bash
uv sync --all-packages
uv pip install -e 'plugins/plugin-cad-jig/python[cad]'
uv run python -c "from atomc_plugin_cad_jig import cad; print(cad.build123d_available())"
```

## Design decisions

- **Tool name is `generate`, not the brief's literal `cad.generate`.** The frozen manifest schema
  only allows `^[a-z0-9]+(?:[_-][a-z0-9]+)*$` for tool/CLI names (no dots), and the orchestrator
  confirmed the plugin namespace supplies the qualified surface: `cad-jig:generate` (mirroring
  `plugin-atopile`'s `compile` → `atopile:compile`). Watch id uses the same style: `cad:generate`.
- **Manifest exposed as a mapping.** `CadJigPlugin.__atomc_manifest__` is the raw manifest dict,
  not the SDK's pydantic `PluginManifest`. The daemon's discovery (`_resolve_entry`) validates the
  attribute with its own strict `Manifest` model and rejects a foreign pydantic model; the SDK's
  `conformance`/`get_manifest` accept a mapping. The dict is still validated against the shared
  JSON Schema at import (`validate_manifest`).
- **Defaults mirror the IR contract.** Missing `mechanical` settings fall back to the documented
  defaults (plate 1.5/14/19.05, wall 2.0, clearance 0.4, jig 5.0/P75-E2/2.54); a missing outline
  or USB connector is a derivation error surfaced as a gate `SKIP`.
- **USB opening floor.** A connector bbox height below 3.2 mm is floored to the USB-C opening
  default; the cutout centre still follows the connector's Z centre.
- **Collision uses the 2D projection** of component bboxes and keepouts, per the brief; Z is only
  used for the enclosure height fit.
- **Artifact recording is best effort.** Files are reported only after export; a failed
  `/mechanical` transact does not pretend the files are absent. Paths are stored relative to the
  process CWD when possible.

## Deviations from contract

- Tool name deviation as above (orchestrator-approved; no contract change).
- `__atomc_manifest__` is a mapping rather than the SDK's `PluginManifest` (daemon compatibility;
  see "Root changes needed").
- PNG/GLB renders are intentionally skipped for now (brief allows this; follow-up).

## Open issues

- **build123d/OCP not installed locally**, so only the unavailable path is exercised in CI; the
  actual solid builders and STEP/STL export are covered by import-time unit checks only. If the
  orchestrator installs the `cad` extra, run the optional exercise above once.
- **PNG renders** for multimodal/studio previews are a follow-up; GLB export is also not produced.
- Artifacts are appended/replaced in `/mechanical/artifacts`; repeated generation replaces prior
  cad-jig records by id and leaves other producers' records untouched.

## Root changes needed

1. **Regenerate and commit `uv.lock`.** The `plugins/*/python` workspace glob already includes the
   new member; `uv sync --all-packages` rewrote `uv.lock` locally. Per the orchestrator this
   regeneration was left **uncommitted** in this worktree. CI's `uv sync --all-packages` resolves
   it, but the merged lock should be regenerated and committed by the orchestrator.
2. **Plugin SDK conformance bug (WP-2.2).** `atomc_plugin_sdk.conformance()` re-validates
   `manifest.model_dump(mode="json")`, which always includes `runtime.ts: null`; the shared schema
   rejects the null, so conformance reports `MANIFEST_INVALID` for every Python-only plugin. The
   regression test is `xfail`ed with this reason. Fix: dump with `exclude_none=True` (or allow
   `null` for absent runtimes) in `conformance.py`.
3. **Daemon discovery (WP-2.3), optional.** `_resolve_entry` should accept the SDK's pydantic
   `PluginManifest` (e.g. `Manifest.model_validate(obj.model_dump())`), so plugins can keep the
   documented `@atomc_plugin` manifest object instead of exposing a raw mapping.
