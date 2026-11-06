# Your first build

::: info Current status
`atomc build` is implemented in the CLI as a daemon DAG runner. The full hardware pipeline below is still staged: most hardware plugins/backends have not landed, and an empty or incomplete pipeline is never presented as a successful hardware result.
:::

A build walks the hardware DAG from source to artifacts, stopping at every gate:

```
atomc build
```

## Intended full build path

This is the planned Phase 4+ flow. The CLI can start or attach to the daemon and request a DAG run, but the atomc hardware plugins that perform these steps are not implemented yet.

1. **Connect.** The CLI connects to `atomcd` over the frozen JSON-RPC/WebSocket contract.
2. **Schedule.** Installed plugins provide watch/produces declarations. The daemon can represent and run DAG nodes, but this repository does not yet contain the atopile/QMK/CAD/sourcing project plugins.
3. **Compile electrical sources.** The planned atopile plugin will populate `/electrical` and `/layout` from project sources.
4. **Build firmware.** The planned QMK plugin will produce firmware from `/keyboard`; direct `qmk compile` is available separately if QMK is installed.
5. **Simulate supported paths.** The planned Renode plugin will test only demonstrated CPU/peripheral behavior. Renode is not USB-HID or physical-key proof.
6. **Generate CAD.** The planned CAD plugin will produce and check enclosure/plate/jig artifacts.
7. **Evaluate sourcing.** The planned sourcing plugin will collect offers/quotes and evaluate budget gates.

When domain plugins exist, DAG nodes can record input/output hashes and producer metadata in `/provenance`.

## Artifacts

| Artifact                  | Current source/status                                                                        |
| ------------------------- | -------------------------------------------------------------------------------------------- |
| `system_ir.json`          | Example fixture exists; daemon can own and persist it.                                       |
| `.elf` / `.bin` / `.uf2`  | Buildable directly with QMK and its local toolchain; atomc plugin generation is future work. |
| `.repl` / `.resc`         | Planned Renode plugin; atomc does not generate it yet.                                       |
| `.step` / `.stl` / `.glb` | Planned CAD plugin; atomc does not generate it yet.                                          |
| BOM CSV + fab quote       | Planned sourcing plugin; atomc does not currently fetch offers or quotes.                    |

## The example to try

`examples/atomc-pad` (3×3 macropad) is the smaller source/IR fixture; `examples/atomc-keeb` (4×12 ortholinear) is the larger target. Both are described in [Examples](/examples/).

```bash
cd examples/atomc-pad
atomc build          # requires the daemon and its build plugins
```
