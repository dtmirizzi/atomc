# Examples

atomc ships two real hardware projects as living fixtures. They are used as golden targets in CI and
as the walk-throughs in these docs.

| Example | Size | Role |
| ------- | ---- | ---- |
| [`atomc-pad`](/examples/atomc-pad) | 3×3 macropad | Fast dev fixture used in Phase 4 before scaling up |
| [`atomc-keeb`](/examples/atomc-keeb) | 4×12 ortholinear (48 keys) | The full end-to-end target: a real, orderable keyboard |

Both are atopile projects with a QMK `qmk/` folder, a hand-written `system_ir.json` that validates
against the [IR schema](/architecture/contracts/ir-schema), and an `atomc.config.ts` with budget
gates. `atomc-keeb` additionally has plate, case and pogo-jig definitions and a 3D viewer placeholder
for its generated `.glb`.

::: info Planned
The examples are seeded in Phase 1 (WP-1.6); the full vertical slice — `atomc build` producing IR,
firmware, `.repl` and CAD goldens — lands in Phase 4 (WP-4.5).
:::
