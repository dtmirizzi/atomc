---
layout: home

hero:
  name: atomc
  text: The Atom Compiler
  tagline: Compile declarative hardware descriptions into verified physical systems — circuits, firmware, enclosure, test jig, and supply chain.
  actions:
    - theme: brand
      text: Get started
      link: /guide/
    - theme: alt
      text: Architecture
      link: /architecture/
    - theme: alt
      text: View on GitHub
      link: https://github.com/dtmirizzi/atomc

features:
  - title: One IR, every domain
    details: A single Pydantic-validated System IR holds electrical, layout, keyboard, firmware, mechanical, sourcing, fabrication and orders nodes — with revisions and subtree locks so many agents can work at once.
  - title: Reactive hardware DAG
    details: Plugins declare what IR subtrees and files they watch. atomc builds a content-hashed DAG, runs only what is stale, and records provenance for every node.
  - title: Gate-driven swarm
    details: Deterministic gates (ERC, QMK compile & matrix scan, plate cutouts, pogo spacing, BOM stock) wake the domain agent that owns the failure, until the design converges.
  - title: Circuits → firmware → enclosure
    details: atopile circuits, Renode-emulated QMK firmware, build123d switch plates, cases and pogo-pin bed-of-nails jigs — all generated from the same IR.
  - title: Real example, not a toy
    details: atomc-keeb is a 48-key ortholinear keyboard with hot-swap MX sockets, an STM32F411, USB-C, and QMK firmware — built end to end through the pipeline.
  - title: Orderable by construction
    details: Keyless sourcing from the public LCSC/JLCPCB catalogues, budget gates, fab quotes and an orders ledger keep cost and availability inside the loop.
---

## The story in one pass

```
atopile circuits ──▶ System IR ──▶ Renode firmware ──▶ build123d enclosure + pogo jig
                         │
                         ├──▶ LCSC/JLCPCB BOM + fab quotes
                         └──▶ tracked orders
```

`atomc` is driven by a reactive hardware DAG and a transactional, gate-driven multi-agent swarm
harness. You describe the hardware; the compiler coordinates the tools that turn it into something
you can build, test and order.

- **Status:** pre-alpha. Phase 0 (environment) and Phase 1 (monorepo + core IR) are active.
- **Roadmap and decisions:** see the [master plan](/plan/master) and the
  [work-package status board](/plan/).
- **The example:** read the [atomc-keeb walkthrough](/examples/atomc-keeb).
