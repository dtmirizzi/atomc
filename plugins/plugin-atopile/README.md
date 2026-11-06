# atomc-plugin-atopile

Built-in atomc plugin that turns [atopile](https://atopile.io) projects and their generated
KiCad boards into typed IR data, and verifies the electrical/layout result with four gates.

| Kind  | Id                                | What it does                                                        |
| ----- | --------------------------------- | ------------------------------------------------------------------- |
| tool  | `atopile.compile`                 | Runs `ato build` and writes components/nets/assertions to `/electrical` |
| tool  | `atopile.import_pcb`              | Parses a `.kicad_pcb` with `kiutils` into `/layout`                 |
| gate  | `gate:erc.no_unconnected`         | No net has fewer than two connected pins                            |
| gate  | `gate:erc.assertions`             | Recorded atopile assertions pass (SKIP on unknown)                  |
| gate  | `gate:layout.testpads.min_count`  | At least `MIN_TEST_PADS` test pads exist                            |
| gate  | `gate:layout.testpads.nets_covered` | Every key-matrix net has a test pad                               |

Watches: one `atopile:build` node invalidated by `.ato`/`ato.yaml`/symbol/footprint/`.kicad_pcb`
changes. Produces: `/electrical`, `/layout`.

## Design notes

- **atopile has no supported build API.** The plugin shells out to the `ato` CLI (0.15.9). A
  missing `ato` binary yields a structured `UNAVAILABLE` result, never a fake PASS; outcomes
  trace to the subprocess exit code.
- **`kiutils` is optional.** Without it, `import_pcb` returns `UNAVAILABLE` and `compile` still
  writes BOM-derived components (with a warning). Install with `atomc-plugin-atopile[pcb]`.
- **Gates are pure IR checks** — no subprocess, filesystem or network — so results are
  deterministic given the document revision.
- **Writes are merged, not clobbered.** `/electrical` and `/layout` have inbound references from
  firmware/sourcing/mechanical/keyboard; the plugin unions its output with existing entries and
  drops placement/test-pad references that would dangle.

## Tests

```bash
uv run pytest plugins/plugin-atopile/python
```

The suite passes without `atopile` or `kiutils` installed (the two real-parser tests skip);
with `kiutils` present it also exercises the committed `.kicad_pcb` fixture.
