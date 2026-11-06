# Examples

The repository contains two hardware project fixtures, a 3×3 macropad and a 4×12 keyboard. Their IR and QMK scaffolding can be inspected and the underlying atopile/QMK sources can be built with the required toolchains.

| Example                              | Size                       | Role                                                                |
| ------------------------------------ | -------------------------- | ------------------------------------------------------------------- |
| [`atomc-pad`](/examples/atomc-pad)   | 3×3 macropad               | Small source/IR fixture for development and future pipeline tests   |
| [`atomc-keeb`](/examples/atomc-keeb) | 4×12 ortholinear (48 keys) | Larger keyboard source/IR fixture for the planned hardware pipeline |

Both fixtures include atopile/QMK source scaffolding, hand-written IR that validates against the [IR schema](/architecture/contracts/ir-schema), and an `atomc.config.ts`. The keyboard fixture also has plate/case/jig target definitions. Atomc does not yet generate these artifacts end-to-end.

::: info Current status
The fixtures and some source-level builds are in the repository. The atomc hardware plugins and the end-to-end `atomc build` vertical slice are still planned for Phase 4.
:::
