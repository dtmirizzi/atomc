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

Optional toolchains (QMK, Renode, atopile) are installed by the idempotent bootstrap, which never uses sudo and writes `~/.atomc/env.sh` (no shell-rc changes):

```bash
bash scripts/bootstrap.sh
. ~/.atomc/env.sh   # exports QMK_HOME, PYRENODE_PATH, ...
```

Build an example project end to end — the daemon starts automatically, discovers the plugins, runs the DAG and evaluates every gate:

```bash
node apps/atomc-cli/dist/index.js build --project examples/atomc-pad
# run run-1: 26 node(s), all settled
# gates: 14 pass, 0 fail, 2 skip, 0 error
```

Without the optional toolchains, the toolchain-dependent gates (QMK compile, Renode boot, fab quotes) report an honest `SKIP` with evidence instead of failing silently.

More commands:

```bash
node apps/atomc-cli/dist/index.js doctor          # CLI, daemon, schema and toolchain checks
node apps/atomc-cli/dist/index.js quote --project examples/atomc-pad   # fab quotes (needs vendor credentials)
node apps/atomc-cli/dist/index.js orders --project examples/atomc-pad  # order ledger (draft-only)
```

Every command takes `--json` (one object on stdout, diagnostics on stderr).

## Examples

- `examples/atomc-pad` — 3×3 macropad (fast fixture; QMK firmware compiles with a real QMK tree)
- `examples/atomc-keeb` — 4×12 ortholinear keyboard
- `examples/atomc-drivetrain` — traction-inverter control board modeled on the [openinverter](https://openinverter.org) architecture for a Tesla-style drive unit (non-keyboard domain)
- `examples/atomc-cannode` — small CAN sensor node (non-keyboard domain)

## What works

- **Core IR + contracts**: Pydantic/TS System IR with revisions, subtree locks, JSON-Patch transactions; cross-language round-trip contract tests
- **Daemon**: authenticated loopback RPC, reactive DAG, gate registry, plugin discovery (Python entry points + project-tree manifests), warm kernels
- **Plugins**: atopile (compile + PCB import + ERC), qmk (IR → keyboard.json + real compiles), renode (platform scripts + boot gate), cad-jig (plate/case/jig geometry + mechanical gates), sourcing (vendor adapters + optimizer + BOM gates), orders (draft-only ledger)
- **CLI**: `init`, `build`, `doctor`, `daemon`, `plugin`, `quote`, `orders`, `converge` — honest exit codes; nothing reports a fake PASS
- **Swarm harness**: deterministic transactional agent runner, specialist definitions, convergence scheduler; `atomc converge` requires a host-injected model runtime (reports `unavailable`, exit 3, without one)
- **Studio**: local-first dashboard (build graph, gates, agents, 3D viewer, telemetry) with data-source labeling; demo data is always labeled

## What does not (yet)

- Live vendor calls (no credentials ship with the repo), order placement (draft-only by design), model-provider API keys
- Renode regression checks do not establish real USB-HID behavior; physical validation requires hardware-in-the-loop
- Phase 6: real prototype bring-up and the 1.0 release

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for development setup, and [`PLAN.md`](./PLAN.md) for the full scope board.
