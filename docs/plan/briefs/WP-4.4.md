# WP-4.4 `example-firmware` — QMK keymaps and HIL checklist for pad + keeb

Read `_common.md`, PLAN §§1, 4, 6, 8, 9; the plugin-qmk handoff (`docs/plan/handoffs/WP-4.2b.md`) and plugin (`plugins/plugin-qmk/**`); `examples/atomc-pad/qmk/**` and `examples/atomc-keeb/**` (including its hand-written qmk folder).

## Owned paths
- `examples/atomc-pad/qmk/keymaps/**` and `examples/atomc-keeb/qmk/keymaps/**`
- `examples/atomc-pad/qmk/README.md`, `examples/atomc-keeb/qmk/README.md`
- `examples/*/hil/` (HIL checklists, per-key test scripts if pure-text)
- `docs/plan/handoffs/WP-4.4.md`

Do not edit the plugin packages, root files, the system_ir.json fixtures (they are WP-1.6 golden), or the derived `keyboard.json` files unless a derivation mismatch is proven (then report it instead).

## Deliverables
1. Default keymaps for both fixtures: layers derived from the committed `keyboard.json` layouts (base layer with a sensible default keycode per position; pad gets a small layer set, e.g. base + media/utilities; keeb gets base + one function layer). Must compile with `qmk compile` where a QMK_HOME exists; when it does not, the files are still syntactically validated (balanced parens, keycode whitelist check via a small pure script or documented manual review).
2. A `keymaps/renode` variant for the pad only: debug-console keymap that prints matrix events over UART (per PLAN WP-4.4), clearly labeled for emulation builds, never claimed as USB HID.
3. HIL checklists (`examples/<name>/hil/checklist.md`): every key position, USB enumeration, bootloader entry — explicit "requires physical board + pogo jig" items, no simulated claims.
4. Tests: none in the plugin sense — this is fixture content. Validate with the existing plugin-qmk derivation goldens (they must keep passing untouched) plus a pure Python or bash syntax check committed under your paths that CI-ignores gracefully. If `qmk` exists locally, run both compiles and record results in the handoff.
5. Handoff: exact commands, compile results, deviations, root changes needed (should be none).

## Definition of done
- `uv run pytest plugins/plugin-qmk/python -q` still passes untouched (goldens unchanged).
- Both default keymaps compile (or are recorded as not-compiled for missing QMK_HOME with the validation evidence).
- No claim anywhere that simulation proves USB/HID.
- Conventional commits; push `wp/4.4-example-firmware`; do not merge.
