# atomc-plugin-cad-jig

Mechanical design plugin for atomc. It derives parametric switch-plate, tray-case and pogo-pin
jig models from the unified system IR, runs five pure mechanical gates, and (when `build123d` is
installed) exports STEP/STL artifacts through the `cad-jig:generate` tool.

## What it does

- **Derives model data** (`models.py`) from `/layout` and `/mechanical`:
  - switch-plate cutout centers from IR switch placements, plate/outline bounds;
  - tray-case walls and a USB-C cutout aligned to the IR connector placement;
  - pogo receptacle positions from `/layout` test pads and alignment pins from mounting holes.
- **Gates** (`gates.py`, pure functions over the derived models — no CAD import needed):

  | Gate id | Checks |
  | --- | --- |
  | `gate:mech.plate_switch_cutouts_14mm` | 14 mm cutouts on a 19.05 mm grid |
  | `gate:mech.case_usb_cutout_aligned` | USB-C cutout on the connector's board edge, centred |
  | `gate:mech.pogo_spacing_ge_2p54` | pogo receptacle pitch ≥ 2.54 mm |
  | `gate:mech.jig_no_collision` | pogo drills and alignment pins clear the 2D footprint |
  | `gate:mech.enclosure_clearance` | walls/clearance and components fit the cavity |

- **Tool** `generate`: builds solids with `build123d` **only when importable** and records the
  exported STEP/STL artifacts into `/mechanical`. Without `build123d` it returns an explicit
  `unavailable` result — it never fabricates a STEP file.

## Layout

```
plugins/plugin-cad-jig/
  atomc-plugin.json                     # manifest (kept byte-identical to the packaged copy)
  python/
    pyproject.toml                      # hatchling, src layout, atomc.plugins entry point
    src/atomc_plugin_cad_jig/
      atomc-plugin.json                 # packaged manifest
      models.py                         # pure parametric derivation
      gates.py                          # pure gate checks
      cad.py                            # build123d builders (lazy import)
      plugin.py                         # @atomc_plugin handlers + tool
      errors.py
    tests/                              # pytest suite + atomc-pad IR fixture
```

## Usage

Install the optional CAD extra to generate artifacts:

```bash
uv sync --all-packages
uv pip install -e 'plugins/plugin-cad-jig/python[cad]'
```

Run the tests (no CAD toolchain required):

```bash
uv run pytest plugins/plugin-cad-jig/python
```
