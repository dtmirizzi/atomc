# atomc-core-ir (Python)

Pydantic v2 models for the atomc **unified system IR** (`system_ir.json`), the single
source of truth for the electrical / layout / keyboard / firmware / simulation /
mechanical / sourcing / fabrication / orders / gates / provenance nodes.

This package is the source of truth for the IR schema: the committed JSON Schema at
[`packages/core-ir/schema/system_ir.schema.json`](../schema/system_ir.schema.json) is
generated from these models, and `@atomc/core-ir` (TypeScript) generates its types and
zod schemas from that file.

Contract: [`docs/architecture/contracts/ir-schema.md`](../../../docs/architecture/contracts/ir-schema.md)
(gates: [`gate-result.md`](../../../docs/architecture/contracts/gate-result.md)).

## Install

```bash
uv sync --all-packages
```

## Usage

```python
from atomc_core_ir import SystemIR, apply_patch, acquire_lock, release_lock

ir = SystemIR.load("system_ir.json")          # path | path-string | JSON text | bytes
print(ir.dump())                               # canonical JSON (sorted keys, 2-space)
print(ir.electrical.components[0].mpn)

# Optimistic-concurrency transaction
node_rev = ir.sourcing.meta_.rev
ir2, result = apply_patch(
    ir,
    "/sourcing",
    node_rev,
    [{"op": "replace", "path": "/build_qty", "value": 10}],
    holder="agent:ops-agent#1",
)
print(result.new_rev, result.changed_paths)

# Advisory subtree lock (pure; does not bump rev)
locked = acquire_lock(ir, "sourcing", "agent:ops-agent#1", ttl_s=60, reason="resourcing")
unlocked = release_lock(locked, "sourcing", "agent:ops-agent#1")
```

`SystemIR.load` validates the schema **and** referential integrity (unique ids
document-wide, every `*_ref`/`*_refs` resolves), raising `RefIntegrityError` on failure.

## Schema export

```bash
# print to stdout
uv run --package atomc-core-ir python -m atomc_core_ir.schema \
  > packages/core-ir/schema/system_ir.schema.json

# CI drift check (exit 1 if the committed schema is stale)
uv run --package atomc-core-ir python -m atomc_core_ir.schema --check
```

## Testing

```bash
uv run --package atomc-core-ir pytest packages/core-ir/python \
  --cov=atomc_core_ir --cov-fail-under=90
```

Reusable Hypothesis strategies live in `atomc_core_ir.testing.system_ir_strategy()`
(used by the cross-language contract tests in WP-1.3).

## Notes

- JSON keys are `snake_case`; the per-node concurrency envelope serialises as `_meta`
  (Python field `meta_`).
- Timestamps are RFC 3339 UTC strings ending in `Z`; hashes are `sha256:<64 hex>`.
- Unknown keys are rejected (`extra="forbid"`) except inside plugin `ext` dicts.
- Transactions implement RFC 6902 in-house, so the only runtime dependency is Pydantic.
