# WP-5.1 `plugin-sourcing` — vendor sourcing adapters with cassettes

Read `_common.md`, PLAN §§1, 2, 4, 6, 8, 9; `docs/architecture/contracts/{plugin-manifest,gate-result,ir-schema}.md`; the WP-2.2 plugin SDK; `packages/core-ir/python/src/atomc_core_ir/sourcing.py` (the frozen offer/bom models — `examples/atomc-pad/system_ir.json` `/sourcing` shows the exact target shape); the plugin-atopile/renode/qmk handoffs for the established plugin patterns. No vendor credentials exist: **live vendor calls are never made in tests; without credentials a live call fails closed with an honest UNAVAILABLE — never fabricated stock or prices.**

## Owned paths
- `plugins/plugin-sourcing/**` (package, manifest, adapters, cassettes, tests, README)
- `docs/plan/handoffs/WP-5.1.md`

Do not edit root files (uv.lock regeneration is expected locally; leave uncommitted and flag), other plugins, daemon, SDK or examples.

## Deliverables
1. Python plugin package `plugins/plugin-sourcing/python` (hatchling, src layout, `atomc.plugins` entry point) with a validated manifest: tools `query` (query offers for a BOM entry / mpn / lcsc sku) and `refresh` (re-query all BOM entries and write offers into `/sourcing` through the plugin context); watch `sourcing:refresh` on `/sourcing`; produces `/sourcing`. Tool names are short and namespace-qualified (`sourcing:query`) like the other plugins.
2. Adapter interface (`src/atomc_plugin_sourcing/adapters/base.py`): `query_component(query) -> list[VendorOffer]`, injectable `httpx`-compatible transport; every vendor adapter is a separate module (`lcsc.py`, `mouser.py`, `digikey.py`, `nexar.py`) implementing the same interface against each vendor's documented public response shape. Adapters are honest: missing API key / endpoint unreachable → `Unavailable` result with evidence; malformed response → error result, never partial guesses.
3. Normalization: `VendorOffer` → the frozen IR `Offer` model (vendor, sku, stock, moq, price_breaks, lead_time_days, currency, fetched_at, url) — validation errors are surfaced, not coerced.
4. Cassettes: deterministic recorded-style fixtures under `tests/cassettes/<vendor>/*.json` that model each vendor's documented response format for a handful of fixture parts (the pad's STM32F411/AP2112K/USB4085). They are clearly synthetic (a README notes no live vendor call was ever made; they model documented API shapes only). Tests replay them through an injected transport — no network, no respx dependency needed if the transport is injected; if you add `respx` it must be a test-only dependency matching PLAN §2 (httpx 0.28.1).
5. Caching: TTL cache (configurable, default e.g. 24 h) over fetched offers, keyed by vendor+query, with honest `fetched_at` propagation — cache hits are labeled as such in results.
6. Tests: deterministic pytest suite (adapter normalization goldens per vendor, unavailable/error paths, cache TTL behavior with a fake clock, plugin context writes respect `/sourcing` scopes, manifest conformance, daemon discovery). Ruff/mypy clean.
7. Handoff: exact commands, cassette provenance statement, deviations, root changes needed (uv.lock).

## Definition of done
- `uv run pytest plugins/plugin-sourcing/python -q` passes with no network and no credentials.
- No test or code path can ever emit a PASS/stock/price that did not come from a cassette or a live authenticated call.
- Conventional commits; push `wp/5.1-plugin-sourcing`; do not merge.

## Stop and ask
If the frozen `Offer`/BOM models lack a field a real vendor response needs (e.g. packaging), stop and report the gap rather than inventing an IR field.
