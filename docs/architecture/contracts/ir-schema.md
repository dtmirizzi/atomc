# Contract: `system_ir.json` (IR schema v0.1)

**Status: FROZEN for Phase 1.** Changes require an edit to this file by the orchestrator and a
`schema_version` bump. Sub-agents implement against this; ambiguity → stop and ask.

Source of truth in code: Pydantic v2 models in `packages/core-ir/python/src/atomc_core_ir/`.
JSON Schema is *generated* from those models into `packages/core-ir/schema/system_ir.schema.json`
(committed). TS types + zod schemas are *generated* from that JSON Schema into
`packages/core-ir/ts/src/generated/`.

## 1. Global conventions

| Rule | Value |
|------|-------|
| JSON keys | `snake_case` everywhere (TS keeps snake_case; no camel conversion — one wire format) |
| Units | length **mm** (float), angle **deg**, current **mA**, voltage **V**, temperature **°C**, time **ms** unless the field name says otherwise (`_us`, `_s`, `_days`), money **integer minor units** + ISO-4217 `currency` (default `"USD"`, cents) |
| Coordinates | Board frame: origin = bottom-left of board outline bbox, +X right, +Y up, viewed from **top**. `side: "top" \| "bottom"`. Bottom-side items keep top-view coordinates (no mirroring). Z: 0 = bottom copper, + up |
| Keyboard units | `x_u, y_u, w_u, h_u` in key units (1u = 19.05 mm), origin top-left of layout as in KLE/QMK `layout` |
| IDs | `^[a-z][a-z0-9_]*:[A-Za-z0-9_.\-/]+$` → `<kind>:<slug>`, e.g. `comp:U1`, `net:3V3`, `pad:TP_SWDIO`, `key:K0_3`, `gate:erc.no_unconnected`. IDs are unique within the whole document |
| References | Fields ending `_ref` / `_refs` hold IDs; the loader validates referential integrity (dangling ref = validation error) |
| Timestamps | RFC 3339 UTC strings (`2026-11-04T23:00:00Z`) |
| Hashes | `sha256:<64 hex>` |
| Paths | POSIX, relative to project root (the dir containing `system_ir.json`) |
| Strictness | `extra="forbid"` on every model except `*.ext` dicts (plugin extension point: `dict[str, JSONValue]` keyed by plugin name) |
| Optional nodes | Every top-level domain node except `meta` is optional (`null`/absent) so a project can start empty |
| Canonical form | `json.dumps(sort_keys=True, indent=2, ensure_ascii=False) + "\n"`; lists keep semantic order; `SystemIR.dump()` must be byte-stable for equal models |

## 2. Concurrency fields

Every **top-level domain node** (and only those) carries:

```json
"_meta": { "rev": 7, "lock": null }
"_meta": { "rev": 7, "lock": { "holder": "agent:ee-agent#3", "acquired_at": "...", "expires_at": "...", "reason": "swap U3" } }
```

- `meta.rev` (document) increases by 1 on every successful transaction.
- `<node>._meta.rev` = the document rev at which that node last changed.
- Transactions: `apply_patch(ir, path, base_rev, ops, holder) -> TxResult`
  - `path`: JSON Pointer to a top-level node or a descendant (e.g. `/sourcing`, `/electrical/components`).
  - `base_rev`: the `_meta.rev` of the **top-level node containing path** that the client read.
    If current node rev ≠ base_rev → `ConflictError(current_rev)`.
  - `ops`: RFC 6902 JSON Patch ops, **relative to `path`**.
  - If the node is locked by another holder whose lock is unexpired → `LockedError(holder, expires_at)`.
  - Result re-validated against the full model; invalid → `ValidationError`, no state change.
  - On success: document rev += 1, node `_meta.rev` = new doc rev, returns `TxResult{new_rev, changed_paths}`.
- In Python the field is `meta_` with `alias="_meta"`; serialization always uses aliases.

## 3. Top-level document

```jsonc
{
  "schema_version": "0.1.0",
  "meta": {
    "project_id": "proj:atomc-keeb",
    "name": "atomc-keeb",
    "description": "48-key ortholinear QMK keyboard",
    "created_at": "…", "modified_at": "…",
    "rev": 42,
    "atomc_version": "0.1.0"
  },
  "electrical": Electrical | null,
  "layout": Layout | null,
  "keyboard": Keyboard | null,
  "firmware": Firmware | null,
  "simulation": Simulation | null,
  "mechanical": Mechanical | null,
  "sourcing": Sourcing | null,
  "fabrication": Fabrication | null,
  "orders": Orders | null,
  "gates": Gates | null,
  "provenance": Provenance | null,
  "ext": { "<plugin-name>": { … } }
}
```

## 4. Domain nodes (fields are required unless marked `?`)

### 4.1 `electrical`
```
_meta
source: { kind: "atopile", entry: "main.ato:App", ato_version? }
components: [Component]
  id "comp:U1", designator "U1", mpn?, manufacturer?, value?, description?,
  footprint?: str, lcsc?: str ("C12345"), package?: str, dnp: bool=false,
  attributes: dict[str,str]={}, pins: [Pin]
    Pin: { number: str, name?: str, net_ref?: "net:…" }
nets: [Net]
  id "net:3V3", name "3V3", class?: "power"|"ground"|"signal"|"diff"|"usb"|"other", voltage_v?: float
assertions: [Assertion]   // atopile `assert` statements
  id "assert:…", expr: str, status: "pass"|"fail"|"unknown", message?
erc: [ErcViolation]
  id, rule: str, severity: "error"|"warning", message, refs: [id]
```

### 4.2 `layout`
```
_meta
source?: { kind: "kicad_pcb", path, sha256? }
outline: { polygon: [[x,y],…] (closed, ≥3 pts, mm), thickness_mm: float=1.6 }
layers: int=2
placements: [Placement]
  component_ref "comp:U1", x, y, rotation_deg, side
test_pads: [TestPad]
  id "pad:TP_SWDIO", net_ref, x, y, side="bottom", diameter_mm=1.0,
  kind: "pogo"|"edge"|"tag_connect"="pogo", label?
mounting_holes: [Hole]  id "hole:H1", x, y, diameter_mm, plated: bool
keepouts: [Keepout]     id, polygon, side, kind: "component"|"copper"|"pogo"
```

### 4.3 `keyboard` (optional domain node)
```
_meta
matrix: { rows: int≥1, cols: int≥1, diode_direction: "COL2ROW"|"ROW2COL",
          row_pins: [str] (len=rows, MCU pin names e.g. "B12"),
          col_pins: [str] (len=cols) }
keys: [Key]
  id "key:K0_0", row, col, x_u, y_u, w_u=1.0, h_u=1.0, rotation_deg=0,
  switch_ref?: "comp:SW1", diode_ref?: "comp:D1", label?, keycode_default?: str ("KC_A")
usb: { vid: "0xFEED", pid: "0x0001", manufacturer: str, product: str, device_version: "1.0.0" }
qmk: { keyboard_path: "atomc/keeb", bootloader: str = "stm32-dfu", processor: str = "STM32F411", board?: str }
```
Validation: `(row,col)` unique; row < rows, col < cols; pin list lengths match.

### 4.4 `firmware`
```
_meta
targets: [FwTarget]
  id "fw:main", mcu: "STM32F411CEU6", core: "cortex-m4f",
  memory: [{ name: "flash"|"ram"|…, origin: int, length: int }]
  framework: "qmk"|"zephyr"|"baremetal"|"other",
  source_dir: str, build_cmd?: str,
  artifacts: [Artifact]
peripherals: [PeriphMap]
  id "periph:usart1", kind: "uart"|"gpio"|"i2c"|"spi"|"usb"|"can"|"timer"|"other",
  base_address?: int, signals: [{ name: "TX", pin: "A9", net_ref? }]
suites: [TestSuite]
  id "suite:matrix", path, framework: "pytest", last_result?: TestRun
    TestRun: { ran_at, passed: int, failed: int, skipped: int, duration_ms, report_path? }
```
`Artifact` (shared type): `{ id "art:…", kind: str ("elf"|"bin"|"uf2"|"step"|"stl"|"glb"|"png"|"repl"|"resc"|"csv"|"json"|"other"), path, sha256, bytes: int, produced_by?: "plugin:…", produced_at }`

### 4.5 `simulation`
```
_meta
platform: { repl_path?, resc_path?, generated_from_rev?: int }
scenarios: [Scenario]
  id "sim:boot", description?, fault?: { kind: "stuck_key"|"ghost"|"brownout"|"sensor_nack"|"custom", params: dict }
captures: [Capture]  id, kind: "uart"|"gpio"|"wavedrom"|"hid", path, scenario_ref?
```

### 4.6 `mechanical`
```
_meta
pcb_bbox: { min: [x,y,z], max: [x,y,z] } ?
component_bboxes: [{ component_ref, min, max }]
enclosure?: { kind: "tray"|"sandwich"|"none", wall_mm, clearance_mm, params: dict }
plate?: { thickness_mm=1.5, cutout_mm=14.0, pitch_mm=19.05, material? }
jig?: { pogo_part: str="P75-E2", min_pitch_mm=2.54, plate_thickness_mm, spring_force_n?, alignment: "mounting_holes"|"pins" }
artifacts: [Artifact]
checks: [MechCheck]  id, kind: "collision"|"clearance"|"pogo_spacing"|"cutout", status: "pass"|"fail", detail?
```

### 4.7 `sourcing`
```
_meta
currency: "USD", build_qty: int ≥1
budget?: { per_unit_minor: int, total_minor?: int }
bom: [BomLine]
  id "bom:…", component_refs: [comp ids], mpn?, lcsc?, qty_per_unit: int,
  offers: [Offer], chosen_offer_ref?, alternates: [ {mpn, lcsc?, reason} ]
    Offer: { id "offer:…", vendor: "lcsc"|"jlcpcb"|"mouser"|"digikey"|"other", sku, stock: int,
             lead_time_days?: int, moq: int=1, price_breaks: [{qty, unit_price_minor}],
             currency, fetched_at, url? }
```

### 4.8 `fabrication`
```
_meta
pcb: { layers, width_mm, height_mm, thickness_mm, finish: "HASL"|"LF-HASL"|"ENIG", color, qty }
assembly?: { side: "top"|"bottom"|"both", parts_count: int }
quotes: [FabQuote]  id, fab: "jlcpcb"|"pcbway"|"other", total_minor, currency, lead_time_days, fetched_at, breakdown: dict[str,int], url?
```

### 4.9 `orders`
```
_meta
orders: [Order]
  id "order:…", vendor, kind: "parts"|"pcb"|"pcba", status: "draft"|"placed"|"paid"|"shipped"|"delivered"|"cancelled",
  lines: [{ sku, qty, unit_price_minor }], total_minor, currency, external_id?, tracking?: [{carrier, number, url?}],
  history: [{ at, status, note? }]
```

### 4.10 `gates`
```
_meta
results: { "<gate id without 'gate:' prefix>": GateResult }  // see gate-result.md
```

### 4.11 `provenance`
```
_meta
nodes: { "<dag node id>": { producer: "plugin:atopile@0.1.0", inputs_hash, outputs_hash, ran_at, duration_ms } }
```

## 5. Required Python API (`atomc_core_ir`)

```python
SystemIR.load(path | str | bytes) -> SystemIR       # validates + ref-integrity
SystemIR.dump(self) -> str                          # canonical form
SystemIR.empty(project_id, name) -> SystemIR
export_json_schema() -> dict                        # == committed schema file
apply_patch(ir, path, base_rev, ops, holder=None, now=None) -> tuple[SystemIR, TxResult]
acquire_lock(ir, node, holder, ttl_s, reason=None, now=None) -> SystemIR   # raises LockedError
release_lock(ir, node, holder) -> SystemIR
class ConflictError, LockedError, RefIntegrityError(ValueError)
```
All functions are pure (return new objects). The daemon owns persistence.

## 6. Required TS API (`@atomc/core-ir`)

```ts
export type SystemIR = …            // generated
export const SystemIRSchema: z.ZodType<SystemIR>   // generated zod 4
export function parseSystemIR(json: unknown): SystemIR
export const SCHEMA_VERSION: "0.1.0"
export type JsonPatchOp = …; export function patch(path: string): PatchBuilder
```
