# Synthetic JLCPCB fabrication cassettes

**No live JLCPCB call was ever made while creating or testing this plugin.** Every file here is a
synthetic, deterministic fixture that models the _documented response shape_ of the JLCPCB PCB
price calculator. Prices, lead times and shipping options are invented for the `atomc-pad` PCB
spec derived from `examples/atomc-pad/system_ir.json` (`/layout` outline + `/sourcing/build_qty`):

- 2 layers, 80 × 80 mm, 1.6 mm, HASL, green, qty 5

Each cassette has three parts:

```jsonc
{
  "_provenance": { "synthetic": true, "fab": "jlcpcb", "note": "…" },
  "request":  { "method": "POST", "path": "/pcb/calculate", "body_contains": "…" },
  "response": { "status_code": 200, "json": { "code": 200, "data": { … }, "message": "…" } }
}
```

`tests/test_fab/_fab_cassettes.py` replays these through `httpx.MockTransport`; the request block
selects the cassette and an unmatched request fails like a dead network. Adding a cassette
requires no network access.

Goldens in `tests/test_fab/goldens/` snapshot the normalized request body and the resulting
`FabQuote` at the fixed test timestamp `2026-11-05T12:00:00Z`. They are committed fixtures, not
live data.

Do not treat these values as real JLCPCB prices. Before production use, re-check the request
fields and the `JOP-HMAC-SHA256` signing scheme against the login-gated JLCPCB documentation.
