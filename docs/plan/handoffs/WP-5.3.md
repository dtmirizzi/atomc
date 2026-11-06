# WP-5.3 `fab-quotes` — handoff

Branch `wp/5.3-fab-quotes` · package `plugins/plugin-sourcing/python` · manifest
`plugins/plugin-sourcing/atomc-plugin.json`.

## What was built

1. **JLCPCB fabrication adapter** (`fab/jlcpcb.py`, base at `fab/base.py`): maps the frozen
   `PcbSpec` (+ optional `Assembly`) onto the documented JLCPCB PCB price-calculator request body
   (`orderType`/`pcbParam` with numeric `pcbColor`/`surfaceFinish` enums, `assemblyParam`), signs
   it with the documented `JOP-HMAC-SHA256` scheme, and parses the `{code,data,message}` envelope
   into a frozen `atomc_core_ir.FabQuote` (deterministic `quote:jlcpcb_<hash>` id, `total_minor`,
   `currency`, `lead_time_days`, `breakdown` = pcb/shipping/assembly, `url`, `fetched_at`).
   Injectable `httpx.BaseTransport`. Missing `JLCPCB_APP_ID`/`JLCPCB_ACCESS_KEY` or an unreachable
   endpoint → honest `UNAVAILABLE`; a malformed/untrusted response → `ERROR`; neither ever carries
   a partial quote.
2. **Spec + budget derivation** (`fab/spec.py`): `/fabrication/pcb` when present, otherwise derived
   from `/layout` (layers, outline bbox, thickness) with documented defaults for finish/color and
   the quantity from `/sourcing/build_qty`. No `/fabrication` node is written into the examples.
   The gate budget comes from `/sourcing/budget.total_minor`, else a documented default
   (`DEFAULT_FAB_BUDGET_MINOR = 10_000`, i.e. USD 100.00); the chosen source is always evidence.
3. **Tool `quote_pcb`** (`fab/tools.py`, manifest entry): resolves the spec from the payload, then
   an existing `/fabrication/pcb`, otherwise `/layout`; fetches quotes via `FabService`; and writes
   them into `/fabrication/quotes` through `ctx.ir_transact`, creating the `fabrication` node (with
   its `pcb` spec) when absent and merging by quote id when present. `write=false` fetches without
   mutating. No trustworthy quote → `UNAVAILABLE`/`ERROR` and the IR is left untouched.
4. **Watch `fab:quote`**: pure invalidation node on `/layout` (see design decisions).
5. **Gate `fab.quote_under_budget`** (`fab/gates.py`): pure, always runnable. Cheapest fetched
   quote ≤ budget → `PASS`; over budget → `FAIL` with the cheapest quote's breakdown; no quotes →
   `SKIP` ("no quotes fetched yet"); un-validatable stored quotes → `ERROR`. Owner `ops-agent`,
   severity `blocking`, `after: ["fab:quote"]`.
6. **Synthetic cassettes + goldens**: `tests/test_fab/cassettes/jlcpcb/` (pad 5 pcs, and a PCBA
   variant) model the documented request/response shape; `tests/test_fab/goldens/` snapshot the
   normalized request body and `FabQuote` at `2026-11-05T12:00:00Z`. A README states no live call
   was ever made.
7. **Tests** (49, all offline): request-mapping goldens, response→`FabQuote` normalization,
   enum/lead-time/color mapping, deterministic ids, missing-credentials / unreachable / rejected-auth
   / error-code / missing-data / malformed-price paths, spec derivation and budget fallbacks,
   fake-context create/merge/write=false/no-data writes, gate PASS/FAIL/SKIP/ERROR and budget
   evidence, and a **real-daemon `IRStore`** create+merge path. An autouse socket kill-switch
   proves no network. Manifest conformance covers the new tool/gate/watch/handlers.

## How to verify (exact commands)

```bash
# from the worktree root
uv run pytest plugins/plugin-sourcing/python -q          # 100 passed
uv run ruff check plugins/plugin-sourcing/python          # clean
uv run ruff format --check plugins/plugin-sourcing/python # clean
uv run mypy plugins/plugin-sourcing/python/src            # clean
pnpm exec biome check plugins/plugin-sourcing/atomc-plugin.json plugins/plugin-sourcing/README.md \
  plugins/plugin-sourcing/python/src/atomc_plugin_sourcing/fab plugins/plugin-sourcing/python/tests/test_fab

# full Python workspace (CI shape: root pyproject, --import-mode=importlib)
uv run pytest -q                                          # 687 passed, 3 skipped, 1 xfailed*
```

\*Pre-existing WP-4.3 SDK-conformance xfail, unrelated to this branch.

## Design decisions

- **Honesty at the adapter boundary.** Every `FabQuote` traces to a parsed response; the adapter
  raises typed failures and `FabAdapter.quote` converts them to non-partial results. Parse builds
  the quote only after the whole envelope validates.
- **`fab:quote` watches `/layout`, not `/fabrication`.** The daemon infers a producer→consumer edge
  whenever one watch's plugin `produces` scope covers another watch's `ir` pointers; watching
  `/fabrication` from this plugin while also producing it created a `fab:quote ↔ sourcing:refresh`
  cycle (`CycleError`). Watching only the external `/layout` input keeps the DAG acyclic and still
  invalidates quotes when board geometry changes.
- **Create-node transaction shape.** An absent node is read as `None` from the IR root (the daemon's
  `store.read` raises `MissingNodeError` for absent nodes), so the tool builds the whole node and
  submits `[{"op":"add","path":"","value":{...}}]` with `base_rev=0`, mirroring `IRStore.map_upsert`.
  This path is covered by a real-`IRStore` test.
- **No cache.** The sourcing TTL cache is keyed for component queries; fabrication quotes are
  user/agent-invoked and merged by deterministic id, so `FabService` has no cache (`force` is
  accepted for tool-schema stability only).
- **PCBA is modelled but secondary.** The optional `assembly` maps to `assemblyParam` and parses
  `assemblyPrice` into the breakdown; no live behaviour is claimed.

## Deviations from contract (should be none)

- **`fab:quote` IR pointers** are `/layout` (not `/fabrication`) for the DAG-cycle reason above; the
  contract only fixes the watch id, not its pointers.
- **Fabrication budget source.** The frozen `fabrication` model has no budget field, so the gate
  reads the project budget at `/sourcing/budget.total_minor` and falls back to a documented default.
  No IR field was invented.
- **Shared files touched that the brief did not list as exclusively owned** (unavoidable; both
  WP-5.2 and WP-5.3 extend the same plugin):
  - `src/atomc_plugin_sourcing/plugin.py` — added the `fab_service` wiring and the `quote_pcb_tool`
    / `check_quote_under_budget` handlers (kept additive and minimal).
  - `tests/test_manifest.py` — relaxed WP-5.1's exact-set assertions to superset assertions so
    WP-5.2/WP-5.3 manifest additions do not break it.
    The orchestrator should expect merge conflicts here when WP-5.2 lands.
- **JLCPCB wire details** (endpoint path `/api/overseas/openapi/pcb/calculate`, signing scheme, exact
  `data` field names) are modelled from public/documented descriptions, not a live call; they must
  be re-checked against the login-gated JLCPCB docs before production use. Cassettes are synthetic.

## Open issues

- No JLCPCB credentials exist in this repo, so live quoting has never been exercised. Real schema
  drift will surface as `ERROR` or `UNAVAILABLE`, never as a fabricated quote.
- Only the JLCPCB adapter ships; `fab` is `"jlcpcb"|"pcbway"|"other"` in the IR but
  `_SUPPORTED_FABS` is `("jlcpcb",)`. Adding PCBWay is a new module behind the same `FabAdapter`.
- Cassettes and goldens are synthetic by design; do not treat their prices as real.

## Root changes needed

- None. No new dependency was added (`uv.lock` unchanged); no root config/code was edited.
