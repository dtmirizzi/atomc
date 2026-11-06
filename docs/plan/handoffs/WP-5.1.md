# WP-5.1 `plugin-sourcing` — handoff

Branch `wp/5.1-plugin-sourcing` · package `plugins/plugin-sourcing/python` · manifest
`plugins/plugin-sourcing/atomc-plugin.json`.

## What was built

1. **Python package + manifest** (`plugins/plugin-sourcing/python`, hatchling `src/` layout,
   `atomc.plugins` entry point `atomc_plugin_sourcing:plugin`). The manifest declares tools
   `query` / `refresh` (qualified by the swarm as `sourcing:query` / `sourcing:refresh`), one
   watch `sourcing:refresh` on `/sourcing`, `produces: ["/sourcing"]` and no gates (BOM gates
   are WP-5.2).
2. **Vendor adapter interface** (`adapters/base.py`): `query_component(query) -> list[VendorOffer]`,
   injectable `httpx.BaseTransport`, typed `VendorUnavailableError` / `VendorResponseError`.
   A missing key, unreachable endpoint, rejected auth or rate limit becomes `UNAVAILABLE`; a
   malformed or incomplete response becomes `ERROR`. Neither failure status can carry offers.
3. **Four vendor modules** (`adapters/lcsc.py`, `mouser.py`, `digikey.py`, `nexar.py`) parsing
   each vendor's documented public shape. LCSC is keyless (endpoint override via `LCSC_API_BASE`),
   Mouser uses `MOUSER_API_KEY`, DigiKey uses a caller-supplied `DIGIKEY_ACCESS_TOKEN` (+ optional
   `DIGIKEY_CLIENT_ID`), Nexar uses `NEXAR_ACCESS_TOKEN`/`NEXAR_TOKEN`.
4. **Normalization** (`normalize.py`): `VendorOffer` → frozen `atomc_core_ir.Offer` with
   deterministic `offer:<line>_<vendor>_<sku>` ids. Pydantic validation errors raise
   `NormalizationError`; nothing is coerced. Nexar maps to IR `vendor: "other"` (see deviations).
5. **TTL cache** (`cache.py`): in-memory, keyed by vendor + query, default 24 h (configurable via
   `ATOMC_SOURCING_CACHE_TTL_S` or per-call `ttl_s`), injectable clock. Hits preserve the original
   `fetched_at` and are labelled `cached: true` in the vendor result and normalized offer.
6. **Tools** (`tools.py`): `query` accepts `bom_line_id`, `mpn` and/or `lcsc` plus vendor
   selection/force/TTL and returns normalized offers with per-vendor status/evidence. `refresh`
   re-queries every BOM line, writes `/sourcing/bom/<i>/offers` (and a consistent
   `chosen_offer_ref`) through `ctx.ir_transact("/sourcing", rev, ops)`, and leaves the IR
   untouched when no trustworthy data is available. Tool statuses are `OK`, `UPDATED`, `SKIP`,
   `UNAVAILABLE` or `ERROR` — never `PASS`.
7. **Synthetic cassettes + goldens**: 12 response-shape fixtures under
   `tests/cassettes/<vendor>/` for `C60442`/`STM32F411CEU6`, `C51118`/`AP2112K-3.3TRG1` and
   `C165948`/`USB4085-GF-A`, replayed through `httpx.MockTransport`; per-vendor normalization
   goldens in `tests/goldens/`. `tests/cassettes/README.md` states explicitly that no live vendor
   call was ever made.
8. **Tests** (51): adapter goldens for all vendors/parts, missing-credentials, unreachable,
   rejected-auth, malformed and partial-response paths, cache TTL with a fake clock, service
   aggregation, tool BOM lookup, refresh transaction shape/scope, no-data leave-unchanged,
   normalization errors, manifest conformance and real daemon entry-point/project discovery.
   An autouse socket kill-switch proves the suite makes no network calls.
9. Plugin `README.md` documenting tools, credentials, statuses and cassette provenance.

## How to verify (exact commands)

```bash
# from the worktree root
uv sync --all-packages
uv run pytest plugins/plugin-sourcing/python -q          # 51 passed
uv run ruff check plugins/plugin-sourcing/python         # clean
uv run ruff format --check plugins/plugin-sourcing/python # clean
uv run mypy plugins/plugin-sourcing/python/src           # clean

# full Python workspace (includes daemon discovery and every existing plugin)
uv run pytest -q                                          # 558 passed, 3 skipped, 1 xfailed*
```

\*The xfail is the pre-existing WP-4.3 SDK conformance issue, unrelated to this branch.

`uv sync --all-packages` regenerates `uv.lock` (new workspace member); that root file is left
uncommitted per the brief.

## Design decisions

- **Honesty at the adapter boundary.** Adapters raise typed failures; `VendorAdapter.query`
  converts them into non-partial results. Parsing builds the offer list only after the complete
  documented response has validated, so a bad second part discards the first.
- **No `respx` dependency.** `httpx.MockTransport` + a cassette matcher (`tests/_sourcing_cassettes.py`)
  keeps replay deterministic and avoids a new test dependency; `httpx>=0.28.1` is the only runtime
  addition and matches PLAN §2.
- **Own TTL cache rather than the daemon cache.** `PluginContext.cache` is currently a plain dict
  without TTL semantics, so the plugin owns an injectable `OfferCache`; a daemon TTL cache could
  replace it later without changing tool contracts.
- **`refresh` does not choose offers.** It updates offers and preserves `chosen_offer_ref` only
  when that id still names a refreshed offer; otherwise it clears it to keep referential integrity.
  Selecting offers under constraints is WP-5.2.
- **Pure invalidation watch.** `sourcing:refresh` has no node handler; mutation happens through the
  `refresh` tool, consistent with the manifest contract's watch semantics.
- **Nexar is an aggregator.** The frozen IR `Offer.vendor` enum is
  `lcsc|jlcpcb|mouser|digikey|other`, so Nexar offers normalize to `"other"` while the query
  report retains `adapter_vendor: "nexar"` and the seller SKU/URL. No IR field was invented.

## Deviations from contract (should be none)

- **Nexar → IR `vendor: "other"`** because the frozen enum has no `nexar` member. Provenance is
  kept in the tool report. If a first-class aggregator vendor is wanted, that is an IR schema
  change (orchestrator-owned), not a plugin change.
- **Mouser/DigiKey/Nexar require an MPN.** An LCSC-only query yields `UNAVAILABLE` for those
  adapters with evidence that no request was made; it is not reported as an empty result.
- **Manifest tool names are `query` / `refresh`**, not literal `sourcing:query`. The shared
  manifest schema only permits `^[a-z0-9]+([_-][a-z0-9]+)*$`; the swarm's qualified namespace is
  `sourcing:*`, matching the other plugins.
- No gates are declared in this WP (none were requested; WP-5.2 owns `bom.*` gates).

## Open issues

- The LCSC endpoint is unofficial and may change; `LCSC_API_BASE` is the escape hatch. Cassettes
  model the documented public JSON shape only.
- DigiKey/Nexar OAuth token acquisition and refresh are out of scope; callers supply a bearer
  token. A future adapter can add the token exchange behind the same injected transport.
- Live vendor response drift has not been exercised (no keys, no live calls). Real drift will
  surface as `ERROR` or `UNAVAILABLE`, never as fabricated data.
- The TTL cache is per-process/in-memory; it is not shared across daemon restarts or workers.
- Cassettes and goldens are synthetic by design; do not treat their stock/prices as real.

## Root changes needed

- **`uv.lock`**: `uv sync --all-packages` added the new workspace member and its `httpx`
  dependency. The file is modified but intentionally uncommitted (root-owned). The orchestrator
  should commit the regenerated lock with this branch.
- No root code/config changes are required. No other plugin, daemon, SDK or example file was
  edited.
