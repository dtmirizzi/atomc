# WP-5.2 `sourcing-optimizer` — offer selection, alternates and BOM gates

Read `_common.md`, PLAN §§1, 4, 6, 8, 9; the frozen sourcing models in `packages/core-ir/python/src/atomc_core_ir/sourcing.py`; the WP-5.1 handoff (`docs/plan/handoffs/WP-5.1.md`) and `plugins/plugin-sourcing/**` (the package you extend); `examples/atomc-pad/system_ir.json` `/sourcing` (budget, build_qty, bom with offers). The optimizer is **pure**: constraints in, selections out — no vendor calls.

## Owned paths
- `plugins/plugin-sourcing/python/src/atomc_plugin_sourcing/optimizer/**`
- `plugins/plugin-sourcing/python/tests/test_optimizer/**`
- the plugin manifest (`atomc-plugin.json` + `manifest.py`) — add only your three gates
- `plugins/plugin-sourcing/README.md` (optimizer section)
- `docs/plan/handoffs/WP-5.2.md`

Keep edits outside your module dirs minimal and isolated (the `bom.*` gate handlers may live in `optimizer/gates.py`); WP-5.3 works in `src/atomc_plugin_sourcing/fab/**` concurrently — do not touch it.

## Deliverables
1. Selection engine (`optimizer/select.py`): given the `/sourcing` subtree (bom entries with offers, budget, build_qty, constraints), choose per-entry offers minimizing total cost subject to: stock ≥ qty (build_qty × qty_per_unit), MOQ, lead-time cap, optional vendor-count cap and per-vendor budget weights; produce `chosen_offer_ref` + ranked `alternates` per entry. Tie-breaking is deterministic (documented: e.g. cost, then stock, then sku lexicographic). Infeasible entries produce explicit reasons, never a silent best-effort pick.
2. Mutation: a tool `optimize` that writes chosen refs and alternates into `/sourcing` through the plugin context (respect scopes); registered in the manifest alongside the WP-5.1 tools.
3. Gates (pure, always runnable, no vendor calls): `bom.all_in_stock` (every entry's chosen offer covers qty), `bom.cost_under_budget` (extended cost vs `budget.total_minor` and `per_unit_minor` — both reported), `bom.lead_time_under_days` (max chosen lead time vs the configured cap, default from IR or a documented default with evidence). Owner annotations match the contract: `bom.cost_under_budget` is shared ownership (ops + ee) per the agent routing tables.
4. Tests: deterministic pytest suite — golden selection on the pad fixture; constraint violations (stock, MOQ, lead time, budget) each yield the documented FAIL with evidence; alternates ranking; tie-breaking determinism; infeasibility reasons; gate PASS/FAIL on mutated fixtures; manifest conformance. Ruff/mypy clean.
5. Handoff: exact commands, the selection algorithm summary, deviations, root changes needed (uv.lock only if dependency changed — none expected).

## Definition of done
- `uv run pytest plugins/plugin-sourcing/python -q` passes (all suites, including WP-5.1's) with no network.
- Every gate outcome traces to IR data; the optimizer never calls a vendor.
- Conventional commits; push `wp/5.2-sourcing-optimizer`; do not merge.
