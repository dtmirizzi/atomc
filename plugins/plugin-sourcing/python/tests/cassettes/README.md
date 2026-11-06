# Synthetic vendor cassettes

**No live vendor call was ever made while creating or testing this plugin.** Every file here is
a synthetic, deterministic fixture that models the *documented response shape* of its vendor.
The values (stock, lead times, prices, part numbers) are invented for a handful of fixture parts
from the `atomc-pad` BOM:

- `C60442` / `STM32F411CEU6`
- `C51118` / `AP2112K-3.3TRG1`
- `C165948` / `USB4085-GF-A`

Each cassette has three parts:

```jsonc
{
  "_provenance": { "synthetic": true, "vendor": "…", "note": "…" },
  "request":  { "method": "GET|POST", "path": "/…", "params"?: {…}, "body_contains"?: "…" },
  "response": { "status_code": 200, "json": { … } }
}
```

`tests/_cassettes.py` replays these through `httpx.MockTransport`; the request block selects the
cassette and an unmatched request fails like a dead network. Adding a cassette requires no
network access.

Vendor shapes modeled:

| Directory | Documented shape                                                   |
| --------- | ------------------------------------------------------------------ |
| `lcsc/`   | Public LCSC product JSON (`code`, `result.productCode`, prices)    |
| `mouser/` | Mouser Search API v1 (`SearchResults.Parts`, `PriceBreaks`)        |
| `digikey/`| DigiKey ProductSearch v4 (`Products`, `StandardPricing`)           |
| `nexar/`  | Nexar GraphQL `supSearchMpn` (`sellers[].offers[].prices`)         |

Goldens in `tests/goldens/<vendor>.json` snapshot the normalized adapter offers at the fixed
test timestamp `2026-11-05T12:00:00Z`. They are committed fixtures, not live data.
