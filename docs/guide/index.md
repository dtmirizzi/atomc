# What is atomc?

`atomc` — **The Atom Compiler** — compiles declarative hardware descriptions into *verified physical
systems*. It takes an atopile circuit description and drives it all the way to an emulated firmware
build, a printable enclosure and pogo-pin test jig, a real bill of materials with live pricing, and a
tracked order.

The name is a pun: like a compiler lowers source to machine code through typed intermediate
representations, atomc lowers a hardware description through a typed **System IR** and a set of
verification **gates** until every domain agrees the design is buildable.

## The pipeline

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

## Core ideas

**One IR.** Electrical, layout, keyboard, firmware, simulation, mechanical, sourcing, fabrication,
orders, gates and provenance are all nodes of a single `system_ir.json`. Every node carries a
revision and an optional lock, which is what makes concurrent multi-agent editing safe.

**A reactive DAG.** Each plugin declares the IR subtrees and files it watches. The daemon turns those
declarations into a dependency graph, hashes inputs, and re-runs only the nodes that are stale.

**Gates, not vibes.** A gate is a deterministic check — ERC has no unconnected nets, QMK compiles,
every keypress injects to the right keycode, the plate has 14 mm switch cutouts, pogo pins are spaced
at least 2.54 mm, every BOM line is in stock. A `FAIL` names the agent that owns the fix.

**A swarm that converges.** Agents receive gate failures, claim the IR subtree they own, make a
change through a transaction, re-run the affected DAG, and re-check their gates. Repeat until
everything is `PASS`.

## Where to go next

- [Install atomc](/guide/install) and run your [first build](/guide/first-build).
- Understand the [architecture](/architecture/) and the frozen
  [contracts](/architecture/contracts/ir-schema).
- See what a real target looks like: [atomc-keeb](/examples/atomc-keeb).

::: warning Pre-alpha
Interfaces are frozen (the contracts under `/architecture/contracts/`) but most features are not
implemented yet. Pages mark anything still **planned**. The [master plan](/plan/master) is the source
of truth for scope.
:::
