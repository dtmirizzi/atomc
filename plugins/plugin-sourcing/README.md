# atomc-plugin-sourcing

Built-in atomc plugin for BOM sourcing. It queries vendor adapters, normalizes every result
into the frozen IR `Offer` model, caches successful responses with a TTL, and writes refreshed
offers into `/sourcing`.

| Kind  | Qualified name       | What it does                                                        |
| ----- | -------------------- | ------------------------------------------------------------------- |
| tool  | `sourcing:query`     | Query offers for a BOM line, MPN or LCSC part number (read-only)     |
| tool  | `sourcing:refresh`   | Re-query every BOM line and write offers into `/sourcing`            |
| tool  | `sourcing:optimize`  | Choose offers and rank alternates under constraints (pure)           |
| watch | `sourcing:refresh`   | Pure invalidation node watching `/sourcing`                          |
| gate  | `bom.all_in_stock`   | Every chosen offer covers the required quantity and its MOQ          |
| gate  | `bom.cost_under_budget` | Extended chosen cost is within total and per-unit budgets         |
| gate  | `bom.lead_time_under_days` | Every chosen offer has a verifiable lead time within the cap    |

Manifest tool names are the short `query` / `refresh` / `optimize`; the swarm namespaces them as
`sourcing:query` / `sourcing:refresh` / `sourcing:optimize`. The plugin declares
`produces: ["/sourcing"]`. The three `bom.*` gates are blocking and owned by `ops-agent` in the
manifest; the swarm routing table additionally wakes `ee-agent` for `bom.cost_under_budget`
(shared ownership), which the single-owner manifest field cannot express.

## Optimizer

`sourcing:optimize` is pure: it reads `/sourcing`, never calls a vendor, and writes only
`chosen_offer_ref` and `alternates` through the plugin context. For each BOM line it computes the
required quantity (`build_qty × qty_per_unit`), the order quantity (`max(required, MOQ)`), and the
price-break unit price. Candidates must have enough stock for the order quantity, a matching
currency, a known lead time within the cap, and at least one price break. Infeasible lines are
written with `chosen_offer_ref: null` and explicit reasons; there is no silent best-effort pick.

Ranking is deterministic: `(effective extended cost, -stock, vendor, sku, offer id)`. The
effective cost is the actual extended cost multiplied by an optional per-vendor budget weight.
With no vendor cap each line picks its cheapest feasible offer. With `vendor_count_cap`, every
vendor subset up to the cap is enumerated and the subset minimizing total effective cost wins;
ties prefer fewer vendors and then lexicographic vendor names. If no subset covers every line,
the optimizer maximizes covered lines and reports the rest as infeasible.

Constraints are supplied in the tool payload because the frozen `Sourcing` model has no
constraints field:

```json
{
  "constraints": {
    "lead_time_cap_days": 14,
    "vendor_count_cap": 2,
    "vendor_budget_weights": { "lcsc": 1.0, "mouser": 1.2 }
  },
  "dry_run": false
}
```

`lead_time_cap_days` defaults to the documented 14-day cap; pass `null` to disable it. The gates
use the same 14-day default and carry that provenance in their evidence. `dry_run` reports the
selection without transacting.

## Vendors and credentials

Live calls are **never** made in tests. Without credentials an adapter fails closed with an
honest `UNAVAILABLE` result; it never fabricates stock or prices.

| Adapter | Endpoint / mode                                      | Environment                                   |
| ------- | ---------------------------------------------------- | --------------------------------------------- |
| LCSC    | Public product JSON (`wmsc.lcsc.com`), no API key    | `LCSC_API_BASE` (optional mirror override)    |
| Mouser  | Search API v1                                        | `MOUSER_API_KEY`                              |
| DigiKey | ProductSearch v4, bearer token supplied by the caller | `DIGIKEY_ACCESS_TOKEN`, `DIGIKEY_CLIENT_ID`   |
| Nexar   | GraphQL `supSearchMpn`                               | `NEXAR_ACCESS_TOKEN` (or `NEXAR_TOKEN`)       |

LCSC has no supported public API. The default endpoint is the public web product JSON; set
`LCSC_API_BASE` to point at a permitted mirror (for example a self-hosted `jlcparts` export).

Nexar is an aggregator, and the frozen IR `Offer.vendor` enum has no `nexar` member. Nexar
offers are normalized to `vendor: "other"` while the query report keeps `adapter_vendor:
"nexar"` so provenance is not lost. No IR field was invented.

## Results and honesty

Every adapter returns one of:

- `OK` — a response parsed; an empty offer list means the vendor genuinely matched nothing.
- `UNAVAILABLE` — missing credentials, unreachable endpoint or rejected auth; no offers.
- `ERROR` — a response arrived but was malformed or incomplete; no partial offers.

Tools use the statuses `OK`, `UPDATED`, `SKIP`, `UNAVAILABLE` and `ERROR`. They never emit
`PASS` and never invent inventory, lead times or prices. `refresh` only transacts when at least
one attempted line produced a trustworthy authoritative result; otherwise `/sourcing` is left
unchanged. A transaction replaces a line's `offers` (and clears `chosen_offer_ref` if it no
longer names a refreshed offer); choosing offers is handled by `sourcing:optimize`.

Caching is keyed by vendor + query and defaults to 24 hours. Set
`ATOMC_SOURCING_CACHE_TTL_S` or pass `ttl_s` to a tool call. Cache hits keep the original
`fetched_at` and are labelled `cached: true`, including in the per-vendor evidence.

## Tests

```bash
uv run pytest plugins/plugin-sourcing/python -q
uv run ruff check plugins/plugin-sourcing/python
uv run ruff format --check plugins/plugin-sourcing/python
uv run mypy plugins/plugin-sourcing/python/src
```

The suite injects `httpx.MockTransport` to replay synthetic cassettes from
`tests/cassettes/<vendor>/` and installs an autouse socket kill-switch, so it passes with no
network and no credentials. See `tests/cassettes/README.md` for cassette provenance.
