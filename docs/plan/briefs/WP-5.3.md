# WP-5.3 `fab-quotes` — PCB fabrication quotes and the fab gate

Read `_common.md`, PLAN §§1, 4, 6, 8, 9; the frozen `fabrication` models in `packages/core-ir/python/src/atomc_core_ir/fabrication.py` (`PcbSpec`, `FabQuote`, `Fabrication`); the WP-5.1 handoff and `plugins/plugin-sourcing/**` (the package you extend — its adapter/cassette patterns are yours to reuse). No JLCPCB credentials exist: live quotes fail closed honestly; tests use cassettes only.

## Owned paths
- `plugins/plugin-sourcing/python/src/atomc_plugin_sourcing/fab/**`
- `plugins/plugin-sourcing/python/tests/test_fab/**`
- the plugin manifest — add only your gate and tool entries
- `plugins/plugin-sourcing/README.md` (fab section)
- `docs/plan/handoffs/WP-5.3.md`

WP-5.2 works in `src/atomc_plugin_sourcing/optimizer/**` concurrently — do not touch it. Keep manifest edits isolated to your entries.

## Deliverables
1. JLCPCB quote adapter (`fab/jlcpcb.py`): maps a `PcbSpec` (layers, width/height/thickness, finish, color, qty + optional assembly) to the documented JLCPCB quote request shape, parses the response into the frozen `FabQuote` model (total_minor, currency, lead_time_days, breakdown, url, fetched_at). Injectable transport; missing credentials/unreachable → honest UNAVAILABLE; malformed → error, never a partial quote.
2. Cassettes: deterministic fixtures modeling the documented quote response for the pad's PCB spec (derive the spec from `examples/atomc-pad/system_ir.json` `/layout` + `/mechanical` where available, otherwise a documented default fixture spec — do not invent a `/fabrication` node in the example).
3. Tool `quote_pcb` and watch `fab:quote`: write fetched quotes into `/fabrication/quotes` through the plugin context, creating the `fabrication` node (pcb spec) if absent from the provided spec input — respect produces scopes (`/fabrication` must be declared in the manifest produces alongside `/sourcing`).
4. Gate `fab.quote_under_budget` (pure, always runnable): the cheapest fetched quote for the current pcb spec is ≤ the fabrication budget (from IR or a documented default threshold with evidence); no quotes → SKIP with "no quotes fetched yet" evidence; over budget → FAIL with the breakdown.
5. Tests: deterministic pytest suite (request mapping goldens, response→FabQuote normalization, unavailable/error paths, quote writing through a fake plugin context, gate PASS/FAIL/SKIP on mutated fixtures, manifest conformance). Ruff/mypy clean.
6. Handoff: exact commands, cassette provenance statement (synthetic, documented shapes only), deviations, root changes needed (should be none beyond uv.lock if touched).

## Definition of done
- `uv run pytest plugins/plugin-sourcing/python -q` passes (all suites) with no network.
- No fabricated quotes: every PASS traces to a cassette or live authenticated call.
- Conventional commits; push `wp/5.3-fab-quotes`; do not merge.
