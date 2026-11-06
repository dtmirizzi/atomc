# plugin-orders

Cart building and a **draft-only** order ledger for atomc. Turns chosen `/sourcing` offers into
per-vendor upload files, records draft orders for a human to place, and applies deterministic
mock-carrier tracking.

> **No real order is ever placed.** This plugin never contacts a vendor and never processes a
> payment. `place` writes a `draft` record with an explicit notice; the only carrier that ships
> is the mock carrier, and every result it touches is labeled `mock: true`.

## Tools

| Tool | What it does | Writes |
| --- | --- | --- |
| `build_cart` | Groups chosen BOM offers by vendor, writes vendor CSV/BOM-upload files under the plugin artifact dir, records one DRAFT `/orders` entry per vendor with the artifact ref | `/orders`, artifact files |
| `place` | Records a DRAFT order (from explicit lines or chosen `/sourcing` offers); result states that no vendor was contacted | `/orders` |
| `poll` | Asks the configured carrier (mock only) for a tracking timeline and applies the events | `/orders` |
| `webhook` | Accepts an explicitly-mock carrier webhook payload and appends tracking/history | `/orders` |

Watch nodes: `orders:sourcing` (`/sourcing`), `orders:ledger` (`/orders`). `produces`: `/orders`.

## Cart formats

* `lcsc` — `Comment,Designator,Footprint,LCSC Part #,Quantity`
* `jlcpcb` — `Comment,Designator,Footprint,LCSC Part #`
* `mouser` — `Mouser Part Number,Quantity,Customer Part Number`
* `digikey` — `DigiKey Part Number,Quantity,Customer Reference`
* any other vendor — `SKU,Quantity,Vendor,MPN`

Files land in `<artifact_root>/orders/<vendor>-cart.csv`; the file's `sha256` is recorded in the
draft order's history note (the frozen `Order` model has no artifact field).

## Ledger state machine

`draft → placed → paid → shipped → delivered`, with `cancelled` reachable from
`draft`/`placed`/`paid`. Illegal transitions are rejected and leave `/orders` unchanged.
History timestamps come from an injectable clock.

## Development

```bash
uv sync --all-packages
uv run pytest plugins/plugin-orders/python -q
uv run ruff check plugins/plugin-orders
uv run ruff format --check plugins/plugin-orders
uv run mypy plugins/plugin-orders/python/src
```
