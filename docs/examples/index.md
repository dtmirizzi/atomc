# Examples

The repository contains three hardware project fixtures: a 3×3 macropad, a 4×12
keyboard, and a non-keyboard traction-inverter control board. Their IR (and, for the
keyboard fixtures, QMK/atopile scaffolding) can be inspected; some source-level builds
require the corresponding toolchains.

| Example                                         | Size                       | Role                                                                       |
| ----------------------------------------------- | -------------------------- | -------------------------------------------------------------------------- |
| [`atomc-pad`](/examples/atomc-pad)              | 3×3 macropad               | Small source/IR fixture for development and pipeline tests                 |
| [`atomc-keeb`](/examples/atomc-keeb)            | 4×12 ortholinear (48 keys) | Larger keyboard source/IR fixture for the hardware pipeline                |
| [`atomc-drivetrain`](/examples/atomc-drivetrain) | 120×80 mm control board    | Modeled openinverter-style drive-unit control board, proving the IR is domain-generic |
| [`atomc-cannode`](/examples/atomc-cannode)      | 40×25 mm CAN sensor node   | Non-keyboard fixture proving the IR and gates are domain-generic           |

All fixtures include hand-written IR that validates against the
[IR schema](/architecture/contracts/ir-schema) and an `atomc.config.ts`. The keyboard
fixtures also have plate/case/jig target definitions. `atomc-drivetrain` is a
**modeled fixture only** — it is not a buildable design and has no `/keyboard` node.

The atomc hardware plugins and the end-to-end `atomc build` vertical slice run against
these fixtures; see each example page for the gate outcomes it produces.
