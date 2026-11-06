# atomc — The Atom Compiler

atomc is an open-source hardware engineering project. It brings circuit descriptions, firmware, mechanical design, test fixtures and sourcing under a shared system IR and daemon, with honest, gate-driven verification: **a result is only ever PASS when it traces to real data or a real tool run.**

**Status:** pre-alpha — Phases 0–5 are implemented (see [What works](#what-works)). Docs: https://dtmirizzi.github.io/atomc/ · Plan and shipped-scope board: [`PLAN.md`](./PLAN.md)

## Quickstart

Requires Node 22+, pnpm 10+, Python 3.14 (via [uv](https://docs.astral.sh/uv/)).

```bash
git clone https://github.com/dtmirizzi/atomc.git
cd atomc
pnpm install --frozen-lockfile
uv sync --all-packages
pnpm build
```

(pnpm may print an `Ignored build scripts` notice for esbuild/protobufjs — safe to ignore, or run `pnpm approve-builds` to approve them.)

Install the optional toolchains next — they are **optional** (their gates SKIP without them) but the example output below assumes them. The bootstrap is idempotent, never uses sudo and writes `~/.atomc/env.sh` (no shell-rc changes):

```bash
bash scripts/bootstrap.sh
. ~/.atomc/env.sh   # exports QMK_HOME, PYRENODE_PATH, toolchain PATH...
```

Build an example project end to end — the daemon starts automatically, discovers the plugins, runs the DAG and evaluates every gate:

```bash
node apps/atomc-cli/dist/index.js build --project examples/atomc-pad
# run run-1: 26 node(s), all settled
# gates: 14 pass, 0 fail, 3 skip, 0 error
```

The three SKIPs are honest: `fw.matrix_scan` (HIL-only by design) and `fw.renode_boot` (the
fixture's declared ELF is a placeholder that does not exist on disk — the gate says exactly that).
Debug nets (SWD/UART/BOOT0) pass ERC because their test pads count as connections. With **no optional
toolchains** installed, the toolchain gates SKIP instead; a **present-but-broken** toolchain FAILs
with the real compiler error — atomc never converts a broken tool into a quiet SKIP.

Two things to know when running more examples:

- The daemon is bound to **one project at a time**. Switching `--project` requires
  `atomc daemon stop` first — the CLI refuses to silently build the wrong project.
- The daemon caches the environment it was started with; after changing toolchain env
  (sourcing `env.sh`), stop and let the next command restart it.

Scaffold and build your own project (from the same checkout):

```bash
node apps/atomc-cli/dist/index.js init /tmp/my-board
node apps/atomc-cli/dist/index.js build --project /tmp/my-board
```

More commands:

```bash
node apps/atomc-cli/dist/index.js doctor          # CLI, daemon, schema and toolchain checks
node apps/atomc-cli/dist/index.js quote --project examples/atomc-pad   # fab quotes (needs vendor credentials; exits 3 without)
node apps/atomc-cli/dist/index.js orders --project examples/atomc-pad  # order ledger (draft-only; empty ledger exits 1)
```

Leaf commands take `--json` (one object on stdout, diagnostics on stderr).

## Examples

- `examples/atomc-pad` — 3×3 macropad (fast fixture; QMK firmware compiles with a real QMK tree)
- `examples/atomc-keeb` — 4×12 ortholinear keyboard
- `examples/atomc-drivetrain` — traction-inverter control board modeled on the [openinverter](https://openinverter.org) architecture for a Tesla-style drive unit (non-keyboard domain)
- `examples/atomc-cannode` — small CAN sensor node (non-keyboard domain)

## What works

- **Core IR + contracts**: Pydantic/TS System IR with revisions, subtree locks, JSON-Patch transactions; cross-language round-trip contract tests
- **Daemon**: authenticated loopback RPC, reactive DAG, gate registry, plugin discovery (Python entry points + project-tree manifests), warm kernels
- **Plugins**: atopile (compile + PCB import + ERC gates), qmk (IR → keyboard.json + real `qmk compile` with artifact hashes), renode (platform scripts + boot gate that never treats a file path as a banner), cad-jig (pure model derivation + five mechanical gates; STEP/STL export only when build123d is importable), sourcing (vendor adapters + optimizer + BOM gates), orders (draft-only ledger + cart writers)
- **CLI**: `init`, `build`, `doctor`, `daemon`, `plugin`, `quote`, `orders`, `converge`, `sim`, `jig` — honest exit codes; nothing reports a fake PASS (`sim`/`jig` remain structured stubs)
- **Swarm harness**: deterministic transactional agent runner, specialist definitions, convergence scheduler; `atomc converge` requires a host-injected model runtime (reports `unavailable`, exit 3, without one)
- **Studio**: local-first dashboard (build graph, gates, agents, 3D viewer, telemetry) with data-source labeling; demo data is always labeled

## What does not (yet)

- Live vendor calls (no credentials ship with the repo), order placement (draft-only by design), model-provider API keys
- A present ELF artifact for the Renode boot gate on the example fixtures (they declare placeholders)
- Renode regression checks do not establish real USB-HID behavior; physical validation requires hardware-in-the-loop
- Phase 6: real prototype bring-up and the 1.0 release

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for development setup, and [`PLAN.md`](./PLAN.md) for the full scope board.
