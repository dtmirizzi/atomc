# Plugins

Plugins connect atomc's daemon to engineering tools and services. The v0.1 manifest and Python/TypeScript SDKs are implemented. Project-specific hardware, sourcing and order plugins have not landed yet. A manifest declares watched inputs, produced IR scopes, gates and tools.

Planned built-in plugins (Phase 4+):

| Planned plugin    | Intended writes             | Intended checks                                            |
| ----------------- | --------------------------- | ---------------------------------------------------------- |
| `plugin-atopile`  | `/electrical`, `/layout`    | ERC, assertions, test pads                                 |
| `plugin-renode`   | `/firmware`, `/simulation`  | supported boot/peripheral checks; no assumed USB-HID proof |
| `plugin-qmk`      | `/firmware`, `/keyboard`    | QMK compile, IR pin match                                  |
| `plugin-cad-jig`  | `/mechanical`               | cutouts, spacing, collisions                               |
| `plugin-sourcing` | `/sourcing`, `/fabrication` | stock, cost, lead time, quotes                             |
| `plugin-orders`   | `/orders`                   | order status                                               |

## Language support

The SDKs support Python and TypeScript implementations with the shared `atomc-plugin.json` manifest. A plugin can use the runtime best suited to its host/kernel; both runtimes are not required for every plugin.

## Read next

- [Writing a plugin](/plugins/writing-a-plugin) — the shape of a plugin in TS and Py.
- [Manifest reference](/plugins/manifest) — every field of `atomc-plugin.json`.
- [Conformance](/plugins/conformance) — SDK helpers for testing plugin packages.

The normative definition is the
[plugin manifest contract](/architecture/contracts/plugin-manifest).
