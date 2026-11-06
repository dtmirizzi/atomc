# WP-5.4 `plugin-orders` — cart builder, order ledger and mock carrier tracking

Read `_common.md`, PLAN §§1, 4, 6, 8, 9; the frozen `orders` models in `packages/core-ir/python/src/atomc_core_ir/orders.py` (`Order`, `OrderLine`, `Tracking`, `HistoryEntry`, statuses draft→placed→paid→shipped→delivered); the WP-2.2 plugin SDK; the established plugin patterns (atopile/renode/qmk handoffs). **No real order is ever placed: ordering requires a human with vendor accounts; every mutating tool produces draft records and the mock carrier is explicitly labeled mock.**

## Owned paths
- `plugins/plugin-orders/**`
- `docs/plan/handoffs/WP-5.4.md`

Do not edit root files, other plugins, daemon, SDK or examples.

## Deliverables
1. Python plugin package `plugins/plugin-orders/python` (hatchling, src layout, `atomc.plugins` entry point) with a validated manifest: tools `build_cart` (chosen BOM offers → per-vendor cart, vendor CSV/BOM-upload format files written into the project build dir), `place` (records a draft order into `/orders` with status `draft` and history — it NEVER contacts a vendor; the result says so explicitly), `poll` (asks the configured carrier source for tracking updates), `webhook` (accepts a mock carrier webhook payload, appends tracking/history); watch on `/sourcing` + `/orders`, produces `/orders`.
2. Cart formats: LCSC/JLCPCB BOM upload CSV, Mouser/DigiKey cart CSV — deterministic writers, unit-tested goldens. Files land under the project build dir with artifact refs recorded into `/orders` drafts.
3. Order ledger semantics: all writes go through the plugin context to `/orders` (respect scopes); history entries carry timestamps from an injectable clock; status transitions are validated (draft→placed→paid→shipped→delivered, cancelled) and illegal transitions are rejected with errors.
4. Mock carrier (`carriers/mock.py`): an injectable carrier interface; the mock returns deterministic tracking timelines for fixture tracking numbers and is labeled `mock` in every result. A real carrier adapter would implement the same interface later; none ships now.
5. Tests: deterministic pytest suite (cart goldens per vendor, ledger transitions legal/illegal, place/poll/webhook paths with fake context + fake clock, manifest conformance, daemon discovery). Ruff/mypy clean.
6. Handoff: exact commands, the "no real orders" honesty statement, deviations, root changes needed (uv.lock).

## Definition of done
- `uv run pytest plugins/plugin-orders/python -q` passes with no network.
- No tool output can be read as "an order was placed with a vendor"; drafts and mock tracking are unmistakably labeled.
- Conventional commits; push `wp/5.4-plugin-orders`; do not merge.
