# IR schema browser

The interactive browser below reads `public/schema/system_ir.schema.json`, which `docs:sync` copies
from `packages/core-ir/schema/system_ir.schema.json`. If that generated schema is missing, a
hand-written placeholder built from the [v0.1 contract](/architecture/contracts/ir-schema) is shown
instead, with a banner telling you so.

Regenerate the real schema by building `core-ir`, then re-sync the docs:

```bash
pnpm --filter @atomc/core-ir build
pnpm --filter @atomc/docs sync
```

<SchemaBrowser />

## Notes on the generated schema

- The Python Pydantic models are the source of truth; the JSON Schema is exported by
  `export_json_schema()` and committed at `packages/core-ir/schema/system_ir.schema.json`.
- CI fails on schema drift, so the browser can never show a stale shape.
- TypeScript types and zod schemas are generated from the same file into
  `packages/core-ir/ts/src/generated/`.
