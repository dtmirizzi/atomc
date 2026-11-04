# Architecture

atomc is a monorepo of a Python daemon, a TypeScript CLI and agent harness, and a set of dual-language
plugins that all agree on one frozen set of contracts.

## The system at a glance

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

## Two processes, one IR

- **`atomcd` (Python daemon)** owns persistence. It holds `system_ir.json` in memory, applies
  transactions to it, schedules the DAG, runs gates, and exposes everything over JSON-RPC. Expensive
  kernels — atopile, OCP/build123d, pyrenode3, kiutils — are loaded once and reused (OCP in its own
  worker process, since it is not thread-safe).
- **`@atomc/cli` (TypeScript)** is the user-facing front end. It can start or attach to a daemon and
  speaks the same RPC surface the swarm harness uses.

## Layers

| Layer | Location | Language | Responsibility |
| ----- | -------- | -------- | -------------- |
| Contracts | `docs/architecture/contracts/` | Markdown | Frozen interfaces: IR schema, RPC, plugin manifest, gate result, agent protocol |
| Core IR | `packages/core-ir` | Py + TS | Pydantic models ⇄ JSON Schema ⇄ TS types + zod |
| Daemon | `packages/daemon` | Py | IR store, DAG, gate runner, plugin host, warm kernels |
| Plugin SDK | `packages/plugin-sdk` | Py + TS | `defineAtomcPlugin`, host protocol, conformance kit |
| Swarm harness | `packages/swarm-harness` | TS | pi-ai agent loops, locks, converge-until-PASS |
| Plugins | `plugins/*` | Py + TS | atopile, renode, cad-jig, sourcing, orders |
| CLI | `apps/atomc-cli` | TS | commander-based UX |
| Studio | `apps/atomc-studio` | TS | Phase 3 Vite + React + R3F dashboard |

## Read next

- [Unified System IR](/architecture/ir) — the node model and concurrency semantics.
- [DAG & gates](/architecture/dag-gates) — how work is scheduled and verified.
- [Swarm harness](/architecture/swarm) — how failures get fixed.
- [Distribution](/architecture/distribution) — how this ships.
- [Testing model](/architecture/testing) — what "green" means.

The frozen interfaces themselves live under [Contracts](/architecture/contracts/ir-schema).
