# atomc — Master Plan

> `atomc` (The Atom Compiler) compiles declarative hardware descriptions into verified physical
> systems: atopile circuits → Renode-emulated firmware → build123d enclosures and pogo-pin test jigs →
> live BOM / fab quotes → tracked orders. It is driven by a reactive hardware DAG and a transactional,
> gate-driven multi-agent swarm harness.

Status: **Phase 0 (environment) + Phase 1 (monorepo + core IR) are the active phases.**
This document is the single source of truth for scope, decisions, work breakdown, and sub-agent
orchestration. Update it when a decision changes; do not fork copies.

---

## 0. Decisions log (resolved + defaults)

Items marked **(default)** were chosen by the orchestrator because the user had no stated preference.
Override by editing this table and re-briefing affected agents.

| # | Topic | Decision | Rationale |
|---|-------|----------|-----------|
| D1 | Repo | `~/github.com/dtmirizzi/atomc`, GitHub `dtmirizzi/atomc`, public | user |
| D2 | Python | **3.14.x** (single pinned interpreter via `uv`, `.python-version`) | atopile 0.15.9 requires `>=3.14,<3.15`; build123d 0.13 / OCP 8.0.1 ship cp314 arm64 wheels |
| D3 | Node / PM | Node 25 (≥22 LTS supported), **pnpm 10** workspaces + **turbo 2.11** | user has both installed |
| D4 | Latest libs | Always latest stable at time of scaffold (see §2 version matrix). Renovate keeps them fresh. | user |
| D5 | Renode on macOS | Native **Renode 1.17.0 osx-arm64 portable**; Docker `antmicro/renode` as fallback + CI | 1.17.0 ships arm64 mac dmg |
| D6 | KiCad | Pure-Python `.kicad_pcb` parsing (`kiutils`) for IR extraction; KiCad app optional for atopile layout **(default)** | no hard GUI dep for CLI/CI |
| D7 | Studio | **Phase 3** (with CLI + harness). Vite 8 + React 19 + @react-three/fiber | user |
| D8 | Example | **`examples/atomc-keeb`** — a real, orderable end-to-end keyboard: 4×12 ortholinear (48 keys), Kailh MX hot-swap sockets, per-key 1N4148W diodes, USB-C (5.1 kΩ CC pull-downs, USBLC6 ESD), **STM32F411CEU6** (QMK ChibiOS-supported, Renode STM32F4 platform), SWD + UART + matrix test pads on the bottom for the pogo jig, build123d plate + case + jig | user wants QMK keyboard |
| D9 | Example firmware | **QMK** (latest `qmk_firmware` master, ChibiOS, `keyboards/atomc/keeb` generated from IR: `keyboard.json` matrix pins, layout, USB VID/PID) + default keymap; built with `qmk compile`. QMK compile is the deterministic software gate; Renode coverage is only claimed for proven peripheral paths; USB HID and all-key validation require HIL on a real board | user |
| D10 | LLM provider | OpenRouter via `@mariozechner/pi-ai`; direct Anthropic/OpenAI also supported through pi-ai. Model routing in `atomc.config.ts` **(default)** | matches harness |
| D11 | IR ownership | **Daemon-owned IR** with optimistic versioning; agents mutate via RPC `ir.transact(subtree, baseVersion, patch)` **(default)** | real transactional semantics, one writer |
| D12 | Agent runtime | Swarm agents are **in-process pi-ai agent loops** inside `swarm-harness`, not spawned CLIs | bespoke harness goal |
| D13 | Sub-agent dev tool | herdr sub-agents, kind **`pi`**, model **`openrouter/deepseek/deepseek-v4.1-flash`** thinking `medium` (cost control), one **git worktree + herdr workspace per work package**. Orchestrator (Opus) reviews/merges | user |
| D14 | Merge policy | Orchestrator reviews each WP branch (tests + lint + handoff doc), squash-merges to `main` **(default)** | |
| D15 | License | **Apache-2.0** | user |
| D16 | Naming | npm `@atomc/*`; PyPI `atomc`, `atomc-core-ir`, `atomc-daemon`, `atomc-plugin-*` | |
| D17 | CI | GitHub Actions from day one; Linux runners for Renode/KiCad, macOS runner for OCP smoke | |
| D18 | Docs site | **VitePress 1.6** → GitHub Pages at `https://dtmirizzi.github.io/atomc/` | TS-heavy repo; MD+Vue components for schema browser and 3D viewer |
| D19 | Out of scope (v0) | Real order placement/payment, carrier webhooks beyond a mock, thermal FEA, PCBWay | listed as plugin examples only |
| D20 | Parallelism | ≤5 sub-agents concurrently in Phase 0–2; ≤6 in Phase 3–5 (DeepSeek Flash is cheap; the limit is review bandwidth) | token cost + review bandwidth |

**Resolved by user 2026-11-04:** keyboard+QMK example, Apache-2.0, no vendor API keys, pi sub-agents on DeepSeek V4.1 Flash, Studio in Phase 3.

**Consequences of “no vendor keys”:** Phase 5 adapters use only keyless sources — the public JLCPCB/LCSC parts catalogue (yaqwsx `jlcparts` mirror + LCSC public product JSON), JLCPCB's public PCB price calculator endpoints, and user-supplied CSV. Mouser/DigiKey/Nexar adapters are built against recorded cassettes and activate when a key appears in env.

**Still open (defaults in effect):** keyboard size (4×12 ortho default; a 3×3 macropad `examples/atomc-pad` is used as the fast dev fixture in Phase 4 before scaling to 48 keys).

---

## 1. Architecture summary

```
                 ┌────────────────────────────────────────────────────────────┐
                 │                     apps/atomc-cli  (TS)                   │
                 │  init · build · sim · jig · quote · orders · converge      │
                 └──────────────┬───────────────────────────┬─────────────────┘
                                │ JSON-RPC/WS               │ in-proc
                 ┌──────────────▼───────────────┐  ┌────────▼─────────────────┐
                 │  packages/daemon  atomcd (Py) │  │ packages/swarm-harness   │
                 │  • owns system_ir.json        │◄─┤ (TS, pi-ai)              │
                 │  • DAG scheduler + watchers   │  │ • state machine           │
                 │  • gate runner                │  │ • IR subtree locks        │
                 │  • warm kernels: atopile,     │  │ • @ee @fw @mech @ops      │
                 │    build123d/OCP, pyrenode3,  │  │ • converge-until-PASS     │
                 │    kiutils                    │  └──────────────────────────┘
                 └──────────────┬───────────────┘
                                │ plugin host API (Py) + manifest (TS/Py)
        ┌───────────┬───────────┼───────────┬────────────┐
        ▼           ▼           ▼           ▼            ▼
  plugin-atopile plugin-renode plugin-cad-jig plugin-sourcing plugin-orders
        └───────────┴───────────┴───────────┴────────────┘
                                │ read/write typed IR nodes
                 ┌──────────────▼───────────────┐
                 │  packages/core-ir             │
                 │  Pydantic v2 ⇄ JSON Schema ⇄ TS│
                 └──────────────────────────────┘
```

### 1.1 Unified Hardware IR (`system_ir.json`) — top-level nodes

| Node | Owner plugin | Contents |
|------|--------------|----------|
| `meta` | core | schema version, project id, created/modified, IR revision counter |
| `electrical` | atopile | modules, components (MPN, footprint, value, tolerance), nets, pins, assertions, ERC results |
| `keyboard` | atopile/qmk | optional domain node: matrix `{rows, cols, diode_direction, row_pins, col_pins}`, keys `[{id, row, col, x_u, y_u, w_u, h_u, switch_ref, diode_ref, keycode_default}]`, USB `{vid, pid, manufacturer, product}` — source for QMK `keyboard.json`, plate cutouts, and Renode key injection |
| `layout` | atopile/kiutils | board outline polygon (mm), layer stack, component placements, **test pads** (`id, net, x, y, side, diameter, kind=pogo|edge|tag-connect`) , mounting holes, keepouts |
| `firmware` | renode | targets (MCU, core, flash/ram map), binaries (`.elf/.bin`, sha256), peripheral map (addr → periph → nets), test suites + last results |
| `simulation` | renode | generated `.repl`/`.resc` paths, fault-injection scenarios, waveform captures |
| `mechanical` | cad-jig | PCB bbox, component 3D bboxes, enclosure params, jig params (pogo pitch, spring force, plate thickness), generated artifacts (`.step/.stl/.glb`), collision/clearance results |
| `sourcing` | sourcing | BOM lines ↔ vendor offers (vendor, sku, stock, lead time, price breaks, currency, fetched_at), chosen offer, budget |
| `fabrication` | sourcing | PCB spec (layers, size, finish, qty) + fab quotes (JLCPCB, …) |
| `orders` | orders | carts, placed orders, shipments, status history |
| `gates` | daemon | every gate id → `{status: PASS|FAIL|SKIP|ERROR, evidence, ts, owner_agent}` |
| `provenance` | daemon | DAG node → inputs hash, outputs hash, producer plugin+version |

Every node carries `_rev` and `_lock` (holder agent id, expiry) to support subtree transactions.

### 1.2 Verification gates (initial set)

| Gate id | Plugin | Wakes |
|---------|--------|-------|
| `erc.no_unconnected`, `erc.assertions` | atopile | `@ee-agent` |
| `layout.testpads.min_count`, `layout.testpads.nets_covered` | atopile | `@ee-agent` |
| `fw.qmk_compile`, `fw.matrix_pins_match_ir` | qmk | `@fw-agent` |\n| `fw.renode_boot`, `fw.matrix_scan` (only if proven for target; otherwise evidence-backed SKIP) | renode | `@fw-agent` |\n| `hil.usb_enumerates`, `hil.all_keys_report`, `hil.bootloader_recovery` | physical hardware / pogo jig | human release checklist; later HIL plugin |
| `kb.layout_matches_keymap`, `kb.diode_per_switch`, `kb.usb_cc_pulldowns` | atopile | `@ee-agent` |
| `mech.plate_switch_cutouts_14mm`, `mech.case_usb_cutout_aligned` | cad-jig | `@mech-agent` |
| `mech.pogo_spacing_ge_2p54`, `mech.jig_no_collision`, `mech.enclosure_clearance` | cad-jig | `@mech-agent` |
| `bom.all_in_stock`, `bom.cost_under_budget`, `bom.lead_time_under_days` | sourcing | `@ops-agent` + `@ee-agent` |
| `fab.quote_under_budget` | sourcing | `@ops-agent` |

---

## 2. Version matrix (latest as of 2026-11-04)

Python (managed by `uv`, pinned in `uv.lock`):

| Package | Version | Notes |
|---------|---------|-------|
| python | 3.14.6 | `uv python install 3.14` |
| pydantic | 2.14.2 | |
| pydantic-settings | 2.16.2 | |
| fastapi | 0.162.0 | daemon HTTP+WS |
| uvicorn | 0.54.0 | |
| watchfiles | 1.3.0 | DAG file watcher |
| structlog | 26.1.0 | |
| networkx | 3.7 | DAG |
| typer | 0.27.3 | `atomcd` CLI |
| httpx | 0.28.1 | vendor adapters |
| atopile | 0.15.9 | **requires py3.14** |
| build123d | 0.13.0 | |
| cadquery-ocp | 8.0.1.1.0 | cp314 arm64 wheel exists |
| kiutils | 1.4.8 | `.kicad_pcb` parsing |
| trimesh | 5.2.0 | collision / glb export |
| pyrenode3 | git `antmicro/pyrenode3@main` (installed 0.0.1, commit recorded in `docs/plan/ENVIRONMENT.md`) | Pythonnet; exports `PYRENODE_PATH` only (legacy `PYRENODE_BIN`/`PYRENODE_PKG` aliases must not be combined) |
| pytest | 9.2.0 | |
| pytest-asyncio | 1.4.1 | |
| ruff | 0.17.3 | |
| mypy | 2.4.1 | strict |
| hatchling | 1.33.0 | build backend |
| datamodel-code-generator | 0.89.0 | *not used for primary models* (hand-written Pydantic is source of truth) |
| mkdocs-material | — | **not used**; VitePress chosen (D18) |

TypeScript (pnpm catalog in `pnpm-workspace.yaml`):

| Package | Version |
|---------|---------|
| typescript | 7.0.2 |
| vitest | 5.1.0 |
| tsup | 9.0.0 |
| turbo | 2.11.10 |
| zod | 4.6.7 |
| @mariozechner/pi-ai | 0.73.1 |
| @mariozechner/pi-agent-core | 0.73.1 |
| commander | 15.0.0 |
| ws | 8.22.1 |
| json-schema-to-typescript | 16.0.0 |
| @biomejs/biome | 2.6.5 |
| @changesets/cli | 3.0.3 |
| vitepress | 1.6.4 |
| three / @react-three/fiber | 0.187.0 / 9.8.2 |
| vite / react | 8.3.5 / 19.3.1 |

External binaries:

| Tool | Version | Install |
|------|---------|---------|
| Renode | 1.17.0 | `renode-1.17.0.osx-arm64-portable.dmg` → `/Applications/Renode.app` or `~/.local/opt/renode` |
| .NET runtime | 8 LTS | `brew install dotnet@8` (pyrenode3 coreclr) |
| arm-none-eabi-gcc | GNU Arm Embedded 13.2.1 (`osx-cross/arm/arm-gcc-bin@13` for QMK); Homebrew core 16.2.0 also installed | Formula install avoids cask's sudo installer; `~/.atomc/env.sh` puts the full toolchain first (core formula lacks newlib specs) |
| cmake, ninja | latest | brew |
| QMK CLI | latest (`uv tool install qmk`) | `qmk setup -H ~/qmk_firmware` (clones qmk_firmware + submodules); toolchain via `brew tap osx-cross/arm` / QMK-recommended arm-none-eabi-gcc |
| KiCad | 9.x (optional) | `brew install --cask kicad` — only for `ato build` layout + viewing |
| gh | present | |

---

## 3. Monorepo layout (final)

```
atomc/
├── PLAN.md                      ← this file
├── README.md  LICENSE  CONTRIBUTING.md  SECURITY.md  CHANGELOG.md
├── .python-version  pyproject.toml  uv.lock           (uv workspace root)
├── package.json  pnpm-workspace.yaml  pnpm-lock.yaml  turbo.json  biome.json  tsconfig.base.json
├── .changeset/                  (TS release notes)
├── .github/
│   ├── workflows/ ci.yml  release-npm.yml  release-pypi.yml  docs.yml  nightly-hw.yml
│   ├── renovate.json
│   └── ISSUE_TEMPLATE/  PULL_REQUEST_TEMPLATE.md
├── docs/                        (VitePress site → GitHub Pages)
│   ├── .vitepress/config.ts
│   ├── index.md  guide/  reference/  plugins/  architecture/  plan/
│   └── public/                  (schema.json, demo .glb, images)
├── scripts/
│   ├── bootstrap.sh             (Phase 0 one-shot installer, idempotent)
│   ├── doctor.py                (→ `atomc doctor`)
│   └── gen-ts-types.ts          (JSON Schema → TS)
├── apps/
│   ├── atomc-cli/               (TS, commander 15)
│   └── atomc-studio/            (Phase 3)
├── packages/
│   ├── core-ir/                 (Py pydantic + TS generated types; dual package)
│   ├── daemon/                  (Py: atomcd)
│   ├── plugin-sdk/              (TS + Py: defineAtomcPlugin, host API)
│   └── swarm-harness/           (TS: pi-ai agents, locks, gate loop)
├── plugins/
│   ├── plugin-atopile/  plugin-renode/  plugin-cad-jig/  plugin-sourcing/  plugin-orders/
├── examples/
│   ├── atomc-pad/               (3×3 macropad dev fixture: ato, qmk/, atomc.config.ts)
│   └── atomc-keeb/              (48-key ortho: ato, qmk/, plate/case/jig, budget gate)
└── tests/
    ├── contract/                (cross-language schema + RPC conformance)
    ├── e2e/                     (atomc build on example; golden artifacts)
    └── fixtures/                (vendor API cassettes, .kicad_pcb, .elf)
```

Each `packages/*` and `plugins/*` directory contains **either** `pyproject.toml`, `package.json`, or both.
Dual packages (core-ir, plugin-sdk, every plugin) have `python/` and `ts/` subfolders with a shared
`manifest.json` at the package root.

---

## 4. Contracts frozen before fan-out

Sub-agents can work in parallel only if interfaces are fixed first. These are written by the
orchestrator (WP-1.0) **before** Phase 1 agents start and may only change via a PLAN.md edit.

1. `docs/architecture/contracts/ir-schema.md` — node list above, naming (`snake_case` JSON, `camelCase` TS via generator), units (mm, mA, °C, USD cents), id format (`<node>:<slug>`), `_rev/_lock` semantics.
2. `docs/architecture/contracts/rpc.md` — JSON-RPC 2.0 over WebSocket `ws://127.0.0.1:7437/rpc` + HTTP `/health`, `/schema`. Methods: `ir.get(path)`, `ir.transact(path, baseRev, jsonPatch)`, `ir.lock/unlock`, `dag.status`, `dag.run(target?)`, `gates.list/run`, `plugins.list`, `tools.call(plugin, tool, args)`, `events.subscribe` (push: `ir.changed`, `gate.result`, `dag.node.start/end`, `log`).
3. `docs/architecture/contracts/plugin-manifest.md` — `atomc-plugin.json` schema: `name, version, watches[], gates[], tools[], cli[], ui[], runtime: {python: entrypoint, ts: entrypoint}`.
4. `docs/architecture/contracts/gate-result.md` — `GateResult{id, status, evidence[], suggestions[], owner_agent}`.
5. `docs/architecture/contracts/agent-protocol.md` — how swarm agents receive gate failures, claim locks, propose patches, and report.

---

## 5. Distribution model

### 5.1 Artifacts

| Artifact | Channel | Consumer |
|----------|---------|----------|
| `atomc` (CLI) | npm `@atomc/cli` (+ `npx @atomc/cli`), **also** a single-file bundle attached to GitHub Releases | end users |
| `atomcd` (daemon) | PyPI `atomc-daemon` (+ `uvx atomc-daemon`), auto-installed by the CLI into `~/.atomc/venv` via `uv` on first run | CLI |
| `atomc-core-ir` | PyPI + npm `@atomc/core-ir` (same version number, lock-stepped) | plugins, daemon, harness |
| `@atomc/plugin-sdk` + `atomc-plugin-sdk` | npm + PyPI | third parties |
| Built-in plugins | PyPI `atomc-plugin-*` + npm `@atomc/plugin-*`; bundled into `atomc` meta-package | |
| `atomc` meta | PyPI `atomc[all]` extras → pulls daemon + all plugins | one-shot `uv tool install atomc[all]` |
| Docker | `ghcr.io/dtmirizzi/atomc:<ver>` (Linux, includes Renode, arm-gcc, KiCad-cli, all Python kernels) and `atomc:slim` | CI, Linux users, hermetic builds |
| Homebrew | `dtmirizzi/tap/atomc` formula wrapping the npm bundle + uv bootstrap (Phase 5+) | mac users |
| Docs | GitHub Pages | everyone |

### 5.2 Versioning & release

- **Single version line across the monorepo** (`0.x.y`) — simpler for a dual-language repo; `changesets` drives TS changelog, `uv version` sync script mirrors to Python packages.
- Tag `v0.x.y` → `release-npm.yml` (pnpm publish with provenance) + `release-pypi.yml` (uv build + Trusted Publishing/OIDC) + GHCR image + GitHub Release with CLI bundle and example artifacts (`atomc-keeb.step`, `.glb`, `.repl`).
- Pre-releases: every merge to `main` publishes `0.x.y-next.<sha>` to npm `next` tag and TestPyPI.
- `atomc doctor` verifies that CLI, daemon, and plugin versions agree and that Renode/OCP/arm-gcc are present.

### 5.3 Install UX target

```bash
npx @atomc/cli init my-board       # bootstraps uv venv, installs atomcd + plugins, runs doctor
atomc build                        # starts/attaches daemon, runs DAG
atomc converge                     # swarm until gates PASS
```

---

## 6. Testing model

| Layer | Tooling | Where | Gate in CI |
|-------|---------|-------|-----------|
| **Unit (Py)** | pytest 9, hypothesis for IR models, `pytest-asyncio` | each Py package | required |
| **Unit (TS)** | vitest 5 | each TS package | required |
| **Static** | ruff + mypy --strict; biome + tsc (tsgo) --noEmit | root | required |
| **Schema contract** | Pydantic → JSON Schema → TS types; round-trip tests: every fixture `system_ir.json` validates in both Py and TS; snapshot of `schema.json` committed, CI fails on drift | `tests/contract` | required |
| **RPC contract** | Spin daemon in-proc, drive with TS client; golden request/response JSON | `tests/contract` | required |
| **Plugin conformance** | `atomc-plugin-sdk` ships `conformance()` that loads a manifest and checks watches/gates/tools are registered and callable; every built-in plugin runs it | plugin dirs | required |
| **Golden artifacts** | `.repl`, `.resc`, BOM CSV, jig `.step` bbox/volume/pogo coordinates compared against committed goldens with tolerances | `tests/e2e` | required (Linux) |
| **Hardware kernel smoke** | atopile compile of atomc-pad; build123d plate/case/jig generation; QMK compile of pad + keeb; Renode smoke (boot or documented unsupported MCU/peripheral); no claims of USB HID proof in Renode | `tests/e2e`, Docker image | required on Linux; macOS runner nightly |
| **Swarm harness** | Deterministic fake LLM (scripted pi-ai provider) → verify gate loop convergence, lock contention, rollback; **recorded** real-model sessions replayed in CI; live-model run nightly with budget cap | `packages/swarm-harness` | required (fake), nightly (live) |
| **Vendor adapters** | httpx + recorded cassettes (`respx`); live calls only with secrets in nightly | `plugins/plugin-sourcing` | required (cassettes) |
| **Mutation/fuzz** | hypothesis on IR patches + JSON-patch transactions (conflict detection) | core-ir, daemon | required |
| **Hardware-in-loop (HIL)** | After a physical prototype exists: flash QMK via SWD/OpenOCD; use pogo fixture to short each row/column and verify keycode via USB HID on a host; test bootloader recovery, USB enumeration, and all matrix positions. Store protocol/results under `tests/hil/`; never gates normal PR CI | optional nightly/release; manual before v1.0 |
| **Simulation boundary** | Renode is a regression aid for CPU/peripheral behavior, not proof of end-user USB HID. Run `fw.qmk_compile` always; only enable `fw.matrix_scan` when the STM32F411 + GPIO + USB/QMK path is demonstrated in the supported Renode model. Otherwise mark SKIP with reason and require HIL before release | CI + hardware release checklist |
| **Perf budget** | daemon warm-kernel build of example < 10 s; IR transact p99 < 20 ms | nightly | advisory |
| **Docs** | VitePress build, link check, schema browser renders | `docs.yml` | required |

Coverage floor: 85 % lines for `core-ir`, `daemon`, `plugin-sdk`, `swarm-harness`; 70 % for plugins.

---

## 7. Documentation & GitHub Pages

- VitePress site in `docs/`, deployed by `.github/workflows/docs.yml` on push to `main` (actions/deploy-pages).
- Sections: **Guide** (install, first build, converge), **Architecture** (IR, DAG, gates, swarm, contracts), **Reference** (auto-generated: CLI commands from commander, RPC methods, JSON Schema browser rendered from `public/schema.json`, plugin manifest), **Plugins** (writing a plugin in TS and Py, conformance), **Examples** (atomc-keeb walk-through with embedded `<model-viewer>` of the pogo jig `.glb` and WaveDrom of a matrix scan + HID report), **Plan** (this document rendered + status board).
- Every package `README.md` is symlinked/included into the site via a `docs:sync` script so docs never drift.
- `typedoc` for TS API, `mkdocstrings`-equivalent via `pydoc-markdown` for Py API (or `griffe` JSON → custom Vue page). Decide in WP-1.6.

---

## 8. Work breakdown

Notation: **WP-<phase>.<n>** · owner sub-agent name · depends-on · deliverables · done-when.
Each WP maps to one herdr worktree workspace + one `pi` agent, briefed from `docs/plan/briefs/WP-x.y.md`.

### Phase 0 — Environment bootstrap (1 agent, runs first, blocking)

**WP-0.1 `bootstrap`** — install & verify all toolchains; write `scripts/bootstrap.sh` + `scripts/doctor.py`.
- Install (verified on macOS arm64; exact idempotent implementation in `scripts/bootstrap.sh`): `uv python install 3.14`; `uv tool install atopile==0.15.9`; `brew install dotnet@8 cmake ninja arm-none-eabi-gcc`; `osx-cross/arm/arm-gcc-bin@13` full toolchain plus AVR/QMK formula dependencies; Renode 1.17.0 osx-arm64 portable → `~/.local/opt/renode-1.17.0`; uv installs QMK CLI and clones firmware into `~/qmk_firmware`; verification venv installs build123d/OCP/kiutils/trimesh/pyrenode3; `pnpm` installs turbo + biome globals without editing shell rc files. Optional: `bash scripts/bootstrap.sh --with-kicad`.
- Verify (encoded in `doctor.py`): `ato --version`, imports for build123d/OCP/kiutils/trimesh, `renode --version`, pyrenode3 imports and starts an F4 platform, full GNU Arm compile probe, `qmk doctor`, GitHub CLI auth, and optional KiCad detection. Renode 1.17.0 smoke uses an available STM32F4 platform (there is no STM32G4 platform in the packaged macOS build).
- Done when: `scripts/bootstrap.sh` is idempotent (second run no-ops), `scripts/doctor.py` exits 0, and `docs/plan/ENVIRONMENT.md` records exact versions + any workarounds (e.g. pyrenode3 env vars, Gatekeeper quarantine on Renode dmg).

### Phase 1 — Monorepo & Unified System IR

**WP-1.0 `contracts`** (orchestrator, before fan-out) — write §4 contract docs + skeleton monorepo files: root `pyproject.toml` (uv workspace members), `pnpm-workspace.yaml` with catalog, `turbo.json`, `biome.json`, `tsconfig.base.json`, `.editorconfig`, `LICENSE`, `README.md` stub, `.github/workflows/ci.yml` stub, `.changeset/config.json`, `renovate.json`. Commit to `main`.

**WP-1.1 `core-ir-py`** — `packages/core-ir/python/atomc_core_ir`
- Pydantic v2 models for every node in §1.1 with strict mode, `extra="forbid"`, units as `Annotated` types, id validators, `_rev/_lock`.
- `SystemIR.load/dump` (canonical JSON: sorted keys, 2-space, trailing newline → stable diffs), `SystemIR.schema()` export → `packages/core-ir/schema/system_ir.schema.json` (committed).
- JSON-Patch transaction helpers: `apply_patch(ir, path, base_rev, patch) -> (ir, new_rev) | ConflictError`.
- Fixtures: `fixtures/minimal.json`, `fixtures/atomc-keeb.json` (hand-written realistic example).
- Tests: pytest + hypothesis (round-trip, conflict detection, schema snapshot), ≥90 % coverage.
- Done when: `uv run pytest` green, `ruff`/`mypy --strict` clean, schema committed, `README.md` + `HANDOFF.md`.

**WP-1.2 `core-ir-ts`** — `packages/core-ir/ts` (depends on WP-1.1 schema file; can start from contracts doc and swap in real schema when ready)
- `scripts/gen-ts-types.ts`: JSON Schema → TS types (`json-schema-to-typescript`) **and** zod 4 schemas (via `json-schema-to-zod` or hand-rolled generator) so TS can validate at runtime.
- `IRClient` helpers: typed path accessors, JSON-Patch builder, rev/lock types.
- Vitest: every Py fixture validates; drift test (regenerate & diff == empty).
- Done when: `pnpm test`, `tsc --noEmit`, biome clean; `@atomc/core-ir` builds with tsup (ESM+CJS+d.ts).

**WP-1.3 `contract-tests`** — `tests/contract`
- Cross-language harness: Python emits fixture → TS validates; TS emits patch → Python applies; property test runs via a small Py⇄TS bridge (`subprocess` with JSON stdin/stdout).
- turbo task `contract` wired into `ci.yml`.
- Done when: CI job passes on Linux + macOS.

**WP-1.4 `ci-release`** — `.github/`
- `ci.yml`: matrix (ubuntu, macos-14) × (py3.14, node 22/25): install uv+pnpm, cache, `turbo run lint test build contract`.
- `release-npm.yml`, `release-pypi.yml` (OIDC Trusted Publishing — WP owner documents the one-time PyPI setup steps for the user), `docs.yml` (Pages), `nightly-hw.yml` stub.
- Dockerfile (`docker/Dockerfile`, multi-stage: base-tools → kernels → atomc) + GHCR publish.
- Done when: CI green on a PR; release workflows dry-run via `workflow_dispatch` with `dry_run=true`.

**WP-1.5 `docs-site`** — `docs/`
- VitePress scaffold, nav per §7, schema browser component reading `public/schema.json` (copied by `docs:sync`), plan status page generated from `PLAN.md`, `<model-viewer>` component placeholder.
- Done when: `pnpm docs:build` passes, `docs.yml` deploys to Pages, Pages enabled on repo (agent runs `gh api` to enable, or documents the click).

**WP-1.6 `example-seed`** — `examples/atomc-pad` + `examples/atomc-keeb`
- `ato` projects (atopile 0.15.9): STM32F411CEU6 + 8 MHz HSE (or 25 MHz per QMK blackpill defs), USB-C receptacle w/ CC pull-downs, USBLC6-2SC6 ESD, 3.3 V LDO (e.g. AP2112K-3.3 / XC6220), SWD + UART + BOOT0 pads, key matrix (pad 3×3, keeb 4×12) of MX hot-swap sockets + 1N4148W diodes; bottom-side test pads for VBUS, 3V3, GND, SWDIO, SWCLK, NRST, UART TX/RX, BOOT0, and every row/col net.
- `qmk/` folder: `keyboard.json` + `keymaps/default/keymap.c` matching the matrix (hand-written now; generated from IR in Phase 4). `qmk compile` must pass against the user's `qmk_firmware` checkout via `QMK_HOME` (symlink keyboard into `keyboards/atomc/`).
- `atomc.config.ts` stub with budget gates (`bom.cost_under_budget`: pad 1500¢, keeb 4500¢ per board at qty 5, excl. switches/keycaps).
- Hand-written `system_ir.json` for each, validated by WP-1.1 models (golden for Phase 4).
- Done when: `ato build` succeeds for both, `qmk compile -kb atomc/pad -km default` and `atomc/keeb` succeed, IR fixtures validate.

Phase 1 fan-out: WP-1.1, WP-1.2, WP-1.4, WP-1.5 are active in parallel; WP-1.6 starts once WP-0.1 has installed QMK and the WP-1.1 schema exists (≤5 agents). WP-1.2 can scaffold from the contract doc while WP-1.1 implements, then validates against the committed schema. WP-1.3 starts when 1.1 and 1.2 land.

### Phase 2 — Plugin SDK & Daemon

**WP-2.1 `plugin-sdk-ts`** — `defineAtomcPlugin()`, manifest zod schema, `watches` glob/JSON-pointer matcher, `gates`/`tools` typing, tool JSON-schema export for pi-ai, conformance test kit, template generator `atomc plugin new`.
**WP-2.2 `plugin-sdk-py`** — Python mirror: `@atomc_plugin` decorator, `PluginHost` protocol (ir read/transact, artifacts dir, logger, cache), conformance pytest plugin.
**WP-2.3 `daemon-core`** — FastAPI + WS JSON-RPC per contract; IR store (in-memory + atomic write to disk + rev counter + per-subtree locks with TTL); plugin discovery (entry points `atomc.plugins` + `atomc-plugin.json` scan); DAG built from `watches` (networkx), incremental scheduling with content hashing; gate runner; event bus; `atomcd serve/status/stop`; structlog.
**WP-2.4 `daemon-kernels`** — warm-kernel registry: lazy singletons for atopile/faebryk, OCP, pyrenode3, kiutils with health checks and reload; thread/process isolation for OCP (not thread-safe); crash recovery.
**WP-2.5 `daemon-client-ts`** — `@atomc/daemon-client`: spawn/attach daemon (`~/.atomc/venv`, uv bootstrap), typed RPC client, event stream, retry; used by CLI and harness.
**WP-2.6 `rpc-contract-tests`** — golden RPC tests, lock contention tests (two clients, conflicting patches), DAG incremental rebuild tests with a fake plugin.

### Phase 3 — Swarm Harness & CLI

**WP-3.1 `cli`** — commander 15 app: `init, build, sim, jig, quote, orders, converge, doctor, daemon {start,stop,status}, plugin {new,list}`; pretty TTY output; `--json`; config loader for `atomc.config.ts` (via `tsx`/`jiti`).
**WP-3.2 `harness-core`** — state machine (`IDLE → PLAN → CLAIM_LOCK → ACT → VERIFY → RELEASE → (FAIL? ESCALATE)`), agent registry, pi-ai `Agent` wrappers with tool bridges to daemon `tools.call`, budget/turn caps, transcript persistence (`.atomc/sessions/*.jsonl`).
**WP-3.3 `harness-agents`** — `@ee-agent`, `@fw-agent`, `@mech-agent`, `@ops-agent` system prompts, tool allow-lists, lock scopes (`electrical.*`, `firmware.*`, `mechanical.*`, `sourcing.*|orders.*`), multimodal datasheet/3D-render inspection tools.
**WP-3.4 `harness-converge`** — gate-failure → agent wake routing, parallel scheduling respecting lock graph, conflict rollback, convergence criteria, human-in-the-loop checkpoints, `atomc converge --max-cost`.
**WP-3.5 `harness-tests`** — scripted fake provider, recorded sessions, nightly live run with cost cap.
**WP-3.6 `studio-shell`** (Vite+React, WS to daemon, 4-pane layout) · **WP-3.7 `studio-3d`** (R3F PCB + plate + case + jig from GLB, test-pad overlay) · **WP-3.8 `studio-telemetry`** (WaveDrom matrix scan, Renode/QMK console stream) · **WP-3.9 `studio-gates-orders`** (gate board, BOM/quote/order table).

### Phase 4 — Core hardware plugins (vertical slice on example)

**WP-4.1 `plugin-atopile`** — compile `.ato` through atopile 0.15 Python API; extract components/nets/assertions/test-points; parse `.kicad_pcb` (kiutils) for outline + pad coordinates; ERC gates.
**WP-4.2 `plugin-renode`** — IR → `.repl` (STM32F411 platform + supported GPIO/UART) + `.resc`; first run compatibility probes for QMK ChibiOS on Renode STM32F411. Test boot/no HardFault and debug UART where feasible. Matrix-injection tests require a proven GPIO model and a QMK-emulation keymap; USB HID is **not** assumed emulated. Unsupported features produce an explicit `SKIP` with evidence, never a false `PASS`. Provide a recorded-HIL checklist and leave full matrix/USB assertions to a connected board + pogo fixture until proven simulatable.
**WP-4.2b `plugin-qmk`** — IR → `keyboards/atomc/<name>/keyboard.json` (matrix pins, diode direction, layout geometry from switch placements, USB ids) + default keymap; `qmk compile` tool + `fw.qmk_compile` gate; artifact `.bin/.uf2` sha into IR.
**WP-4.3 `plugin-cad-jig`** — build123d: PCB solid from outline, component bboxes; pogo-pin bed-of-nails jig (P75 receptacles, alignment pins on mounting holes, clamshell lid); **switch plate** (14 mm cutouts at 19.05 mm pitch from IR switch placements), **case** (tray mount, USB-C cutout aligned to connector); collision + spacing gates; export `.step/.stl/.glb` + PNG renders (for multimodal agents).
**WP-4.4 `example-firmware`** — QMK keymaps for pad + keeb (layers, optional debug console on UART for emulation builds via `keymaps/renode`), QMK compile tests; HIL test script/checklist for every key position, USB HID and bootloader.
**WP-4.5 `e2e-vertical-slice`** — `atomc build` on `atomc-pad`, then `atomc-keeb`, yields IR + QMK firmware + `.repl` + plate/case/jig `.step`; goldens; docs walkthrough with embedded GLB.

### Phase 5 — Supply chain & logistics

**WP-5.1 `sourcing-adapters`** — adapter interface; LCSC (JLCPCB parts mirror / unofficial), Mouser, DigiKey, Nexar; httpx + cassettes; normalization to IR offers; caching with TTL.
**WP-5.2 `sourcing-optimizer`** — pick offers under constraints (cost, stock, lead time, vendor count, MOQ); alternates; `bom.*` gates; wake `@ee-agent` with swap proposals.
**WP-5.3 `fab-quotes`** — JLCPCB quote (PCB + assembly) from layout spec; `fab.*` gate.
**WP-5.4 `plugin-orders`** — cart builder (vendor CSV/BOM upload formats), order records, mock carrier webhook + polling, `atomc orders` TUI table.
**WP-5.5 `cli-quote-orders`** — `atomc quote`/`atomc orders` UX + docs.

### Phase 6 — Hardening & 1.0

Real prototype order of `atomc-keeb` through `atomc orders` (user places payment manually), bring-up with the printed pogo jig + OpenOCD flash plugin, Homebrew tap, docs polish, `v1.0.0`.

---

## 9. Sub-agent orchestration runbook (herdr)

### 9.1 Topology

- Orchestrator (this pi session) stays in `~/github.com/dtmirizzi/atomc` on `main`.
- Each WP: `herdr worktree create --cwd <repo> --branch wp/<id>-<slug> --base main --label "WP-<id>" --no-focus` → returns workspace + root pane. Then `herdr agent start wp-<id> --kind pi --pane <pane> -- --provider openrouter --model deepseek/deepseek-v4.1-flash --thinking medium` (**always** pass the model — the global pi default is Gemini/Opus) and `herdr agent prompt wp-<id> "$(cat docs/plan/briefs/WP-<id>.md)" --wait --timeout 3600000`.
- Agent names: `wp-0-1`, `wp-1-1`, … (herdr regex `[a-z][a-z0-9_-]{0,31}`).
- Poll: `herdr agent wait <name> --until blocked --timeout …` in a loop; on `blocked` read `herdr agent read <name> --source recent-unwrapped --lines 120`, answer, continue.

### 9.2 Brief template (every `docs/plan/briefs/WP-x.y.md`)

```
# WP-x.y <slug>
Role · Context (link PLAN.md §) · Owned paths (exclusive) · Read-only paths · Contracts to honor
Deliverables (checklist) · Definition of done · Commands you must leave green
Constraints: latest versions (see PLAN §2), no edits outside owned paths, no force-push,
commit small, conventional commits, write HANDOFF.md (what/why/how to test/open issues)
Ask the orchestrator (stop and ask) when: contract ambiguity, need a new dependency outside §2,
anything requiring credentials or GUI install.
```

### 9.3 Ownership rules

- A WP owns its directories exclusively. Shared root files (`pyproject.toml`, `pnpm-workspace.yaml`, `turbo.json`, `ci.yml`) are edited **only** by the orchestrator or WP-1.4; agents request changes in `HANDOFF.md` under "root changes needed".
- Contracts (§4) are read-only to agents; ambiguity → stop and ask.
- Generated artifacts (`schema.json`, TS types) are committed by their producer WP only.

### 9.4 Review & merge

1. Agent reports done → orchestrator runs in the worktree: `uv run pytest`, `pnpm -r test`, `turbo run lint typecheck`, reads `HANDOFF.md`.
2. Orchestrator rebases on `main`, resolves, squash-merges, deletes worktree (`herdr worktree remove`).
3. Downstream WPs whose dependencies landed get re-briefed with "rebase on main".

### 9.5 Phase gates

A phase is complete when: all its WPs merged, `ci.yml` green on `main`, docs page for the phase published, `PLAN.md` status table updated, and a `v0.<phase>.0` pre-release tag cut.

---

## 10. Status board

| WP | Owner | Branch | State |
|----|-------|--------|-------|
| WP-0.1 bootstrap | pi / DeepSeek Flash | `wp/0.1-bootstrap` | merged to main; 23 doctor checks pass; repeat bootstrap is idempotent |
| WP-1.0 contracts | orchestrator | main | merged; contracts + uv/pnpm workspaces pushed |
| WP-1.1 core-ir-py | pi / DeepSeek Flash | `wp/1.1-core-ir-py` | merged; 56 pytest tests, 98% coverage; strict mypy/ruff clean |
| WP-1.2 core-ir-ts | pi / DeepSeek Flash | `wp/1.2-core-ir-ts` | merged; 34 Vitest tests, schema generation/typecheck/build pass (uses local TS 5.9 for tsup DTS) |
| WP-1.3 contract-tests | queued | — | next: cross-language round-trip / JSON Patch contract harness |
| WP-1.4 ci-release | pi / DeepSeek Flash | `wp/1.4-ci-release` | PR #1 open; Docker + all CI jobs passed on latest run; awaiting merge |
| WP-1.5 docs-site | pi / DeepSeek Flash | `wp/1.5-docs-site` | merged; VitePress build passes; GitHub Pages enabled at https://dtmirizzi.github.io/atomc/ |
| WP-1.6 example-seed | pi / DeepSeek Flash | `wp/1.6-example-seed` | active; QMK pad build underway; circuit + keeb scaffold still in progress |

---

## 11. Risks

| Risk | Mitigation |
|------|-----------|
| atopile 0.15 pins py3.14 while some kernels lag | Verified OCP cp314 wheel; if any kernel breaks, isolate it in its own uv env launched by the daemon as a subprocess (kernel-per-venv design is allowed by WP-2.4) |
| pyrenode3 is unreleased/pythonnet fragility on macOS | Fallback: drive Renode via its telnet monitor / Robot Framework runner; plugin abstracts the transport |
| OCP not thread-safe | Daemon runs CAD in a dedicated worker process |
| LCSC/JLCPCB have no official API | Adapter with cassette fixtures + clearly marked unofficial endpoint; user-supplied CSV fallback |
| TypeScript 7 (tsgo) ecosystem gaps | Keep `typescript@5.9` as a devDependency escape hatch per package if tooling (vitepress, tsup) lags |
| Sub-agent drift | Frozen contracts, exclusive ownership, HANDOFF.md, orchestrator-only root edits |
| Token cost of swarm tests | Fake provider in CI; live runs nightly with hard cost cap |
