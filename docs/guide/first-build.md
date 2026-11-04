# Your first build

::: info Planned
`atomc build` is **planned** for Phase 3. The flow below is the target contract; each step names the
work package that delivers it.
:::

A build walks the hardware DAG from source to artifacts, stopping at every gate:

```
atomc build
```

## What happens

1. **Start or attach the daemon.** The CLI boots `atomcd` (Python) if it is not already running and
   connects over JSON-RPC/WebSocket at `ws://127.0.0.1:7437/rpc`. See the
   [RPC contract](/architecture/contracts/rpc).
2. **Plan the DAG.** Each plugin's `watches[]` entries become DAG nodes; the daemon wires edges from
   `produces` pointers and hashes every input. Only stale nodes run.
3. **Compile the circuit.** `plugin-atopile` compiles your `.ato` project and extracts components,
   nets, assertions and test points into `/electrical`, then parses the `.kicad_pcb` into `/layout`.
4. **Generate firmware.** `plugin-qmk` emits `keyboards/atomc/<name>/keyboard.json` from the
   `/keyboard` node; `qmk compile` produces the `.bin`/`.uf2` and its sha256 is recorded in IR.
5. **Emulate.** `plugin-renode` builds a `.repl` platform and `.resc` script, boots the firmware, and
   runs the test suites — including injecting every keypress into the matrix.
6. **Fabricate a body.** `plugin-cad-jig` generates the switch plate, case and pogo-pin jig from the
   layout and exports `.step`, `.stl` and `.glb`, then checks clearances and pogo spacing.
7. **Price it.** `plugin-sourcing` refreshes BOM offers from the public LCSC/JLCPCB catalogues and
   evaluates the budget gates.

Every node records inputs hash, outputs hash, producer plugin and version into `/provenance`.

## Artifacts

| Artifact | Produced by | Consumed by |
| -------- | ----------- | ----------- |
| `system_ir.json` | daemon | everything |
| `.elf` / `.bin` / `.uf2` | plugin-qmk | flashing, Renode |
| `.repl` / `.resc` | plugin-renode | Renode, CI |
| `.step` / `.stl` / `.glb` | plugin-cad-jig | printing, the 3D viewer |
| BOM CSV + fab quote | plugin-sourcing | ordering |

## The example to try

`examples/atomc-pad` (3×3 macropad) is the fast fixture; `examples/atomc-keeb` (4×12 ortholinear) is
the full target. Both are described in [Examples](/examples/).

```bash
cd examples/atomc-pad
atomc build          # planned
```
