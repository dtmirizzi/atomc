# atomc-plugin-sourcing

Built-in atomc plugin for BOM sourcing. It queries vendor adapters, normalizes every result
into the frozen IR `Offer` model, caches successful responses with a TTL, and writes refreshed
offers into `/sourcing`.

| Kind  | Qualified name       | What it does                                                        |
| ----- | -------------------- | ------------------------------------------------------------------- |
| tool  | `sourcing:query`     | Query offers for a BOM line, MPN or LCSC part number (read-only)     |
| tool  | `sourcing:refresh`   | Re-query every BOM line and write offers into `/sourcing`            |
| watch | `sourcing:refresh`   | Pure invalidation node watching `/sourcing`                          |

Manifest tool names are the short `query` / `refresh`; the swarm namespaces them as
`sourcing:query` / `sourcing:refresh`. The plugin declares `produces: ["/sourcing"]` and no
gates (BOM gates arrive with WP-5.2).

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
longer names a refreshed offer); choosing offers remains WP-5.2's job.

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
