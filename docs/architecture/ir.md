# Unified System IR

Every part of the pipeline reads and writes a single typed document, `system_ir.json`. The Python
Pydantic models in `packages/core-ir/python` are the **source of truth**; the committed JSON Schema
and the TypeScript types + zod schemas are generated from them.

The full field-level definition is in the frozen [IR schema contract](/architecture/contracts/ir-schema).
This page explains the model and its concurrency semantics.

## Top-level nodes

| Node | Owner plugin | Contents |
| ---- | ------------ | -------- |
| `meta` | core | schema version, project id, timestamps, document revision |
| `electrical` | atopile | modules, components, nets, pins, assertions, ERC results |
| `keyboard` | atopile/qmk | matrix, keys, USB ids, QMK target |
| `layout` | atopile/kiutils | outline, layer stack, placements, test pads, holes, keepouts |
| `firmware` | renode/qmk | targets, binaries, peripheral map, test suites |
| `simulation` | renode | `.repl`/`.resc` paths, fault scenarios, captures |
| `mechanical` | cad-jig | bboxes, enclosure, plate, jig, artifacts, checks |
| `sourcing` | sourcing | BOM lines ↔ vendor offers, chosen offer, budget |
| `fabrication` | sourcing | PCB spec + fab quotes |
| `orders` | orders | carts, orders, shipments, status history |
| `gates` | daemon | gate id → `GateResult` |
| `provenance` | daemon | DAG node → input/output hashes, producer |

Every domain node except `meta` is optional, so a project can start empty and grow.

## Conventions

- JSON keys are `snake_case` everywhere. TS keeps `snake_case` too — there is one wire format.
- Units are explicit: length **mm**, current **mA**, voltage **V**, temperature **°C**, time **ms**
  (unless the field says `_us`, `_s`, `_days`), money as **integer minor units** plus ISO-4217
  `currency` (default `"USD"`, cents).
- IDs match `<kind>:<slug>` — `comp:U1`, `net:3V3`, `pad:TP_SWDIO`, `key:K0_3`,
  `gate:erc.no_unconnected` — and are unique document-wide. Fields ending `_ref`/`_refs` hold IDs, and
  the loader rejects dangling references.
- Models are strict: `extra="forbid"` on every model except plugin extension dicts.
- `SystemIR.dump()` is byte-stable: sorted keys, two-space indent, trailing newline.

## Concurrency: revisions and locks

Each top-level domain node carries `_meta`:

```json
"_meta": { "rev": 7, "lock": null }
"_meta": {
  "rev": 7,
  "lock": { "holder": "agent:ee-agent#3", "acquired_at": "…", "expires_at": "…", "reason": "swap U3" }
}
```

- `meta.rev` is the **document** revision and increments on every successful transaction.
- `<node>._meta.rev` is the document revision at which that node last changed.
- A transaction is `ir.transact(path, base_rev, ops)`:
  - `base_rev` is the `_meta.rev` the client read for the **top-level node containing `path`**.
  - `ops` are RFC 6902 JSON Patch ops, relative to `path`.
  - If the node moved past `base_rev` → `ConflictError(current_rev)`.
  - If another holder's lock is unexpired → `LockedError(holder, expires_at)`.
  - The result is re-validated against the full model; invalid → `ValidationError`, no state change.
  - On success the document rev increments, the node's `_meta.rev` becomes the new document rev, and
    `TxResult{new_rev, changed_paths}` is returned.

All helpers are pure and return new objects — the daemon alone persists.

## Python API (per contract)

```python
SystemIR.load(path | str | bytes) -> SystemIR       # validates + ref-integrity
SystemIR.dump(self) -> str                          # canonical form
SystemIR.empty(project_id, name) -> SystemIR
export_json_schema() -> dict                        # == committed schema file
apply_patch(ir, path, base_rev, ops, holder=None, now=None) -> tuple[SystemIR, TxResult]
acquire_lock(ir, node, holder, ttl_s, reason=None, now=None) -> SystemIR
release_lock(ir, node, holder) -> SystemIR
```

Errors: `ConflictError`, `LockedError`, `RefIntegrityError`.

## TypeScript API (per contract)

```ts
export type SystemIR
export const SystemIRSchema: z.ZodType<SystemIR>
export function parseSystemIR(json: unknown): SystemIR
export const SCHEMA_VERSION: "0.1.0"
export type JsonPatchOp; export function patch(path: string): PatchBuilder
```

## Browse the schema

The generated schema is rendered interactively on the [schema browser](/reference/ir-schema) page.
