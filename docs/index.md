---
layout: home

hero:
  name: atomc
  text: The Atom Compiler
  tagline: One system IR for circuits, firmware, mechanical design, test fixtures and sourcing. The hardware compiler is being built in the open.
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
  - title: One IR, many domains
    details: The Pydantic-validated System IR describes electrical, layout, keyboard, firmware, mechanical, sourcing, fabrication and order data. Revisions and subtree locks are part of the model.
  - title: A daemon and DAG foundation
    details: The daemon provides IR storage, RPC, DAG scheduling and gate-result interfaces. Project-specific hardware plugins that compile designs are still in development.
  - title: Transactional harness core
    details: The deterministic runner applies scoped changes and checks daemon gate results. Specialist definitions, routing and provider wiring are in progress.
  - title: A toolchain roadmap
    details: The planned pipeline connects atopile, QMK, Renode and build123d through the shared IR. The atomc plugins for these tools are not implemented yet.
  - title: Concrete hardware fixtures
    details: The repository includes 3×3 macropad and 4×12 ortholinear keyboard source/IR fixtures. Atomc does not yet build them end to end.
  - title: Supply-chain scope
    details: The IR and plugin contracts include BOM, quote and order data. Vendor sourcing and ordering integrations are planned; no parts are ordered.
---

## What is in the repository

The repository has a typed IR, Python daemon, TypeScript CLI, deterministic harness core and a Studio shell. Hardware backends and the multi-agent coordinator remain future work.

- **Status:** pre-alpha. Phases 0–2 and the initial Phase 3 foundation are merged. The WP-3.3, WP-3.4 and WP-3.5 implementations are pushed on their branches for review; none are merged yet. Hardware plugins and the vertical build pipeline remain.
- **Roadmap:** see the [master plan](/plan/master) and [work-package status board](/plan/).
- **Example:** read the [atomc-keeb fixture walkthrough](/examples/atomc-keeb).
