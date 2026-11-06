# Architecture

atomc is a monorepo with a Python daemon, a TypeScript CLI, a transactional harness core, a Studio interface and dual-language plugins. They share frozen contracts.

## The system at a glance

```
                 ┌────────────────────────────────────────────────────────────┐
                 │                     apps/atomc-cli  (TS)                   │
                 │  init · build · doctor · daemon · plugin · sim…             │
                 └──────────────┬───────────────────────────┬─────────────────┘
                                │ JSON-RPC/WS               │ in-process
                 ┌──────────────▼───────────────┐  ┌────────▼─────────────────┐
                 │  packages/daemon  atomcd (Py) │  │ packages/swarm-harness   │
                 │  • owns system_ir.json        │◄─┤ (TS, provider port)      │
                 │  • DAG scheduler + watchers   │  │ • deterministic runner    │
                 │  • gate runner                │  │ • transactional locks     │
                 │  • kernel registry           │  │ • gate-driven verify      │
                 │  • optional kernel adapters   │  │ • scripted fake provider  │
                 │                               │  └──────────────────────────┘
                 └──────────────┬───────────────┘
                                │ plugin host API (Py) + manifest (TS/Py)
        ┌───────────┬───────────┼───────────┬────────────┐
        ▼           ▼           ▼           ▼            ▼
     planned hardware / CAD / sourcing plugin packages
        └───────────┴───────────┴───────────┴────────────┘
                                │ read/write typed IR nodes
                 ┌──────────────▼───────────────┐
                 │  packages/core-ir             │
                 │  Pydantic v2 ⇄ JSON Schema ⇄ TS│
                 └──────────────────────────────┘
```

## Current implementation scope

The daemon and typed IR/contracts are implemented. The CLI foundation and deterministic harness runner are also in the repository. Specialist definitions and a pi-ai provider adapter are in development, alongside the convergence scheduler. Studio starts with clearly labeled fixture data; a desktop host bridge can supply daemon reads/build requests. Hardware plugins, 3D/telemetry/orders views and physical USB-HID validation remain ahead.

## Two processes, one IR

- **`atomcd` (Python daemon)** owns persistence. It holds `system_ir.json`, applies transactions,
  schedules the DAG, runs gates, and exposes the RPC contract. The kernel registry/loading path exists;
  project-specific hardware compiler plugins are still to come.
- **`@atomc/cli` (TypeScript)** is the user-facing front end. It can start or attach to a daemon and
  speaks the same RPC surface the swarm harness uses.

## Layers

| Layer         | Location                       | Language | Responsibility                                                                     |
| ------------- | ------------------------------ | -------- | ---------------------------------------------------------------------------------- |
| Contracts     | `docs/architecture/contracts/` | Markdown | Frozen interfaces: IR schema, RPC, plugin manifest, gate result, agent protocol    |
| Core IR       | `packages/core-ir`             | Py + TS  | Pydantic models → JSON Schema → generated TS types + runtime validation            |
| Daemon        | `packages/daemon`              | Py       | IR store, DAG, gate runner, plugin host, warm kernels                              |
| Plugin SDK    | `packages/plugin-sdk`          | Py + TS  | `defineAtomcPlugin`, host protocol, conformance kit                                |
| Swarm harness | `packages/swarm-harness`       | TS       | deterministic transactional runner, scoped locks, budgets and gate verification    |
| Plugins       | `plugins/*`                    | Py + TS  | Plugin SDK/runtime contracts exist; hardware/sourcing/order plugins remain planned |
| CLI           | `apps/atomc-cli`               | TS       | commander-based UX                                                                 |
| Studio        | `apps/atomc-studio`            | TS       | responsive Vite + React dashboard; fixture mode and injected trusted host bridge   |

## Read next

- [Unified System IR](/architecture/ir) — the node model and concurrency semantics.
- [DAG & gates](/architecture/dag-gates) — how work is scheduled and verified.
- [Swarm harness](/architecture/swarm) — how failures get fixed.
- [Distribution](/architecture/distribution) — how this ships.
- [Testing model](/architecture/testing) — what "green" means.

The frozen interfaces themselves live under [Contracts](/architecture/contracts/ir-schema).
