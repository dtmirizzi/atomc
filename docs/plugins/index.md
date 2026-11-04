# Plugins

Plugins are how atomc knows about hardware. A plugin declares the IR subtrees and files it watches,
the gates it evaluates, and the tools it exposes to swarm agents. Built-in plugins cover atopile
(circuits), Renode + QMK (firmware), build123d (enclosure and jig), and sourcing/orders.

Built-in plugins (Phase 4+):

| Plugin | Writes | Gates |
| ------ | ------ | ----- |
| `plugin-atopile` | `/electrical`, `/layout` | ERC, assertions, test pads |
| `plugin-renode` | `/firmware`, `/simulation` | boot banner, matrix scan |
| `plugin-qmk` | `/firmware`, `/keyboard` | QMK compile, pin match |
| `plugin-cad-jig` | `/mechanical` | cutouts, spacing, collisions |
| `plugin-sourcing` | `/sourcing`, `/fabrication` | stock, cost, lead time, quotes |
| `plugin-orders` | `/orders` | order status |

## Language support

Every plugin is dual-language: a Python side for the hardware kernels and a TypeScript side for the
manifest and UI, sharing one `atomc-plugin.json` at the package root. Write in whichever language the
work needs; the host loads both.

## Read next

- [Writing a plugin](/plugins/writing-a-plugin) — the shape of a plugin in TS and Py.
- [Manifest reference](/plugins/manifest) — every field of `atomc-plugin.json`.
- [Conformance](/plugins/conformance) — the checks CI runs on every plugin.

The normative definition is the
[plugin manifest contract](/architecture/contracts/plugin-manifest).
