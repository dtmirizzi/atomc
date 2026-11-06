# What is atomc?

`atomc` means **The Atom Compiler**. The project aims to carry declarative hardware designs from
circuit description through firmware, enclosure and test-jig design, then into sourcing and order
tracking. The IR, daemon, CLI foundation and deterministic harness core are implemented. Hardware
generation and the manufacturing workflows are still being built.

Like a software compiler, atomc uses a typed **System IR** and verification gates to keep domain tools
and their outputs tied to one project.

## The pipeline

```
                 ┌────────────────────────────────────────────────────────────┐
                 │                     apps/atomc-cli  (TS)                   │
                 │  init · build · doctor · daemon · plugin · sim…             │
                 └──────────────┬───────────────────────────┬─────────────────┘
                                │ JSON-RPC/WS               │ in-proc
                 ┌──────────────▼───────────────┐  ┌────────▼─────────────────┐
                 │  packages/daemon  atomcd (Py) │  │ packages/swarm-harness   │
                 │  • owns system_ir.json        │◄─┤ (TS, provider port)      │
                 │  • DAG scheduler + watchers   │  │ • deterministic runner    │
                 │  • gate runner                │  │ • transactional locks     │
                 │  • warm kernels: atopile,     │  │ • gate-driven verify      │
                 │    build123d/OCP, pyrenode3,  │  │ • provider port (fake CI) │
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

## Core ideas

**One IR.** Electrical, layout, keyboard, firmware, simulation, mechanical, sourcing, fabrication,
orders, gates and provenance are all nodes of a single `system_ir.json`. Every node carries a
revision and an optional lock, which is what makes concurrent multi-agent editing safe.

**A reactive DAG.** The daemon exposes DAG scheduling and the plugin watch/produces contract. The hardware plugins that compile designs and produce project artifacts are still being built.

**Gates are the intended verification source.** The daemon exchanges deterministic gate results, but the example hardware gates and plugins are not all implemented. A failure can identify its owner; software checks here do not prove real USB-HID behavior.

**Verified state transitions, with orchestration still ahead.** The deterministic harness runner
accepts injected provider decisions, claims IR scopes, applies checked transactions/tools, reruns
DAG/gates, and releases locks. It can return `PASS`, `RETRY`, or `ESCALATE` only from real gate
results. The real pi-ai adapter, specialist agents, and multi-agent converge scheduler are not yet
implemented, so the dashboard/runner does not claim unattended design convergence.

## Where to go next

- [Install atomc](/guide/install) and run your [first build](/guide/first-build).
- Understand the [architecture](/architecture/) and the frozen
  [contracts](/architecture/contracts/ir-schema).
- See what a real target looks like: [atomc-keeb](/examples/atomc-keeb).

::: warning Pre-alpha
The IR, daemon, CLI foundation, deterministic harness core and Studio shell are implemented. Hardware
plugins, specialist agents, convergence orchestration, Studio 3D/telemetry/orders, and physical proof
still remain. Renode is not evidence of USB-HID behavior. The [master plan](/plan/master) tracks scope.
:::
