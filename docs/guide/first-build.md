# Your first build

`atomc build` runs the full hardware DAG: the CLI starts or attaches to the daemon, the daemon
discovers the installed plugins, schedules every watch and gate, and reads the final gate state back
over the frozen JSON-RPC/WebSocket contract.

```bash
node apps/atomc-cli/dist/index.js build --project examples/atomc-pad
# run run-1: 26 node(s), all settled
# gates: 13 pass, 0 fail, 3 skip, 0 error
```

The exact pass/skip mix depends on which toolchains you have installed and sourced:

| Environment | Typical result |
| --- | --- |
| Toolchains installed and `~/.atomc/env.sh` sourced | 13 pass, 0 fail, 3 skip — includes a real `qmk compile` |
| No optional toolchains | the toolchain gates SKIP honestly (`qmk`/`renode` unavailable) |
| Toolchain present but broken | the gate **FAILs** with the real compiler error — atomc never converts a broken toolchain into a quiet SKIP |

`fw.renode_boot` SKIPs on the example fixtures because their declared ELF artifact is a placeholder
that does not exist on disk; the gate reports exactly that. Renode is a regression aid, not
USB-HID proof.

## What a build actually does

1. **Connect.** The CLI ensures a daemon is running for the project (loopback WebSocket, token auth).
   A daemon is bound to **one** project; switching `--project` requires `atomc daemon stop` first —
   the CLI refuses to silently build the wrong project.
2. **Discover.** The daemon loads the plugins (atopile, renode, qmk, cad-jig, sourcing, orders) via
   their `atomc.plugins` entry points.
3. **Schedule.** Plugin manifests declare watches and gates; the daemon derives the DAG (26 nodes on
   the pad example) and runs it.
4. **Gates.** Every gate is evaluated against real IR data or a real tool run. Pure gates (ERC,
   layout test pads, mechanical checks, BOM) always run; toolchain gates run the real subprocess.
5. **Persist.** Gate results and artifacts are recorded into the project's `system_ir.json` and
   `.atomc/artifacts/` — running a build mutates the project's IR file by design.

## Artifacts produced on the pad example

| Artifact | Source |
| --- | --- |
| `atomc_pad_default.bin` (real QMK compile, hashed into `/firmware`) | qmk plugin + real `qmk compile` |
| `.repl` / `.resc` platform scripts | renode plugin (generated from the IR) |
| `.step` / `.stl` solids | cad-jig plugin — **only with build123d importable**; otherwise a structured unavailable result |
| Gate results in `system_ir.json` | the daemon |

## Mechanical gates are IR checks, not CAD verification

The five `mech.*` gates are pure checks over the declared model data (cutout geometry, pogo pitch,
clearances). They can PASS with no CAD toolchain installed, because they verify the **declared
design**, not generated solids. Treat them as design-rule checks; solid export is a separate,
explicitly-optional tool.

## Try the non-keyboard examples

`examples/atomc-drivetrain` (openinverter-style traction control board) and
`examples/atomc-cannode` (CAN sensor node) build with the same one command. Keyboard-specific gates
SKIP with "not a keyboard design" evidence instead of failing — see
[Examples](/examples/).

```bash
atomc daemon stop   # the daemon is per-project
node apps/atomc-cli/dist/index.js build --project examples/atomc-drivetrain
```

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | DAG settled; no blocking gate FAIL |
| 1 | a blocking gate FAILed (or no data, e.g. an empty orders ledger) |
| 3 | daemon/plugin/tool unavailable |
