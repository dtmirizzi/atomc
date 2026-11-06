# WP-5.2 `sourcing-optimizer` — handoff

Branch `wp/5.2-sourcing-optimizer` · package `plugins/plugin-sourcing/python` · manifest
`plugins/plugin-sourcing/atomc-plugin.json`.

## What was built

1. **Pure selection engine** (`src/atomc_plugin_sourcing/optimizer/select.py`). Given a validated
   `Sourcing` model it computes `required_qty = build_qty × qty_per_unit` and
   `order_qty = max(required_qty, MOQ)`, then chooses one offer per BOM line. Candidates must have
   enough stock for the order quantity, a matching currency, at least one price break, and (when a
   cap is set) a known lead time within the cap. The price-break unit price is the largest break
   quantity not exceeding the order quantity (falling back to the smallest break).
2. **Deterministic ranking and alternates.** Candidates rank by
   `(effective extended cost, -stock, vendor, sku, offer id)`. The effective cost is the actual
   extended cost multiplied by an optional per-vendor budget weight. Every non-chosen feasible
   offer becomes a frozen `Alternate` in rank order; the offer id, vendor, order quantity, unit
   price, extended cost, lead time and stock are recorded in `Alternate.reason` because the frozen
   `Alternate` model has no offer-ref field.
3. **Vendor-count cap.** With no cap each line independently picks its cheapest feasible offer.
   With `vendor_count_cap`, every vendor subset up to the cap is enumerated and the subset
   minimizing total effective cost wins; ties prefer fewer vendors and then lexicographic vendor
   names. If no subset covers every line, the optimizer maximizes covered lines and reports the
   rest as infeasible rather than silently violating the cap.
4. **Infeasibility is explicit.** A line with no feasible offer gets `chosen_offer_ref=None` and
   reasons such as insufficient stock, MOQ order quantity above stock, unknown/over-cap lead time,
   currency mismatch, no price breaks, or no offer from the selected vendor set. There is no
   silent best-effort pick.
5. **Tool `sourcing:optimize`** (`optimizer/tools.py`, handler `optimize_tool`). Reads `/sourcing`,
   runs the pure engine, and writes `/bom/<i>/chosen_offer_ref` and `/bom/<i>/alternates` through
   `ctx.ir_transact("/sourcing", rev, ops)`. Supports `dry_run` and a `constraints` payload
   (`lead_time_cap_days`, `vendor_count_cap`, `vendor_budget_weights`). It never calls a vendor.
6. **Three pure gates** (`optimizer/gates.py`, handlers `check_all_in_stock`,
   `check_cost_under_budget`, `check_lead_time_under_days`):
   - `bom.all_in_stock` — every chosen offer covers the required quantity and its MOQ.
   - `bom.cost_under_budget` — extended chosen cost vs `budget.total_minor` and
     `budget.per_unit_minor`; both are reported in evidence even when only one fails.
   - `bom.lead_time_under_days` — every chosen offer has a known lead time within the cap.
   Gates read only IR through the plugin context; no vendor, clock or filesystem access.
7. **Manifest and README.** Added the three blocking gates (owner `ops-agent`, after
   `sourcing:refresh`) and the mutating `optimize` tool. README documents the optimizer, ranking,
   constraints, defaults and gate semantics.
8. **Tests** (`tests/test_optimizer/`): 27 new tests covering the pad golden selection, cheapest
   offer, tie-breaking, lead-time/stock/MOQ/currency infeasibility, vendor-count cap, budget
   weights, alternates, gate PASS/FAIL/SKIP/ERROR paths, tool writes, dry runs, null writes for
   infeasible lines and manifest conformance. The full plugin suite is 79 tests.

## How to verify (exact commands)

```bash
# from the worktree root
uv sync --all-packages
uv run pytest plugins/plugin-sourcing/python -q          # 79 passed
uv run ruff check plugins/plugin-sourcing/python         # clean
uv run ruff format --check plugins/plugin-sourcing/python # clean
uv run mypy plugins/plugin-sourcing/python/src           # clean
```

No network or credentials are used; the existing autouse socket kill-switch still applies.

## Design decisions

- **Constraints live in the tool payload, not IR.** The frozen `Sourcing` model has no constraints
  field, so `optimize` accepts `constraints` and gates use the documented default lead cap. No IR
  schema change was made.
- **Default lead cap is 14 days.** The frozen IR has no configured cap. Fourteen days is the
  maximum lead time in the atomc-pad fixture and a common LCSC/JLCPCB turnaround. Gate evidence
  states this provenance explicitly; `lead_time_cap_days: null` disables the cap for selection.
- **Budget is a gate, not a selection constraint.** Selection minimizes cost among feasible
  offers; `bom.cost_under_budget` reports whether the result fits the budget. This keeps the
  optimizer from hiding a budget failure by refusing to choose anything.
- **MOQ is an order quantity.** Stock must cover `max(required_qty, MOQ)`, because a vendor cannot
  sell the MOQ from less stock. The gate reports the MOQ-specific failure separately.
- **Unknown lead time fails when a cap is active.** An unknown lead time cannot be proven under
  the cap, so it is infeasible rather than assumed zero.
- **Vendor budget weights are objective multipliers.** They let a caller prefer a vendor without
  changing the actual extended cost reported by the gates. The README documents this.
- **Shared cost-gate ownership.** The manifest records `ops-agent` because the frozen manifest
  contract allows one owner. The swarm routing table (`MULTI_OWNER_GATES`) already wakes both
  `ops-agent` and `ee-agent` for `bom.cost_under_budget`; no harness change was needed.

## Deviations from contract (should be none)

- None in the frozen IR, manifest, gate-result or RPC contracts. The optimizer adds no IR fields.
- `Alternate` has no offer-ref field, so the offer id is embedded in `Alternate.reason`; the
  ranked order of the `alternates` list is the ranking.
- The manifest's single `owner_agent` cannot express the shared cost-gate ownership; the existing
  swarm routing table supplies the second owner.

## Open issues

- The vendor-count cap enumerates vendor subsets, which is fine for the small vendor set in this
  project (LCSC/Mouser/DigiKey/Nexar) but would need a different algorithm for a large vendor
  catalogue.
- The 14-day lead cap is a documented default, not project configuration. A future IR/config field
  could replace it without changing the gate contract.
- Vendor budget weights are objective multipliers, not per-vendor spend caps. If per-vendor caps
  are wanted, that is a separate constraint and should be specified explicitly.
- Live vendor data is still out of scope for this WP; the optimizer only consumes offers already
  written by WP-5.1.

## Root changes needed

- None. No root files, lockfiles, CI, daemon, SDK or example files were edited.
