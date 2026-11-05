# @atomc/contract-tests

Cross-language conformance tests for the atomc Unified System IR
(`docs/architecture/contracts/ir-schema.md`). This is a private, non-published
pnpm workspace package that drives the **real** Python models
(`atomc-core-ir`, WP-1.1) and the **real** generated TypeScript types/zod schemas
(`@atomc/core-ir`, WP-1.2) against each other.

## What it checks

- **Round-trips** (`ts/roundtrip.test.ts`) — Python `SystemIR.dump()` output is
  accepted by TS `parseSystemIR()` and matches parsing the source fixture; TS's
  zod-normalized serialization is accepted by Python `SystemIR.load()` and Python's
  canonical `dump()` is accepted by TS again. Runs against both
  `examples/atomc-pad/system_ir.json` and `examples/atomc-keeb/system_ir.json`.
- **Patch transactions** (`ts/patches.test.ts`) — TS builds RFC 6902 patches with
  `patch()`; Python applies them with `apply_patch()` using the owning node's
  `_meta.rev` as `base_rev`. Covers `replace`, `add`, `remove`, invalid-value
  rollback, stale-rev conflict, and lock contention.
- **Fixtures** (`ts/fixtures.test.ts`) — every `packages/core-ir/fixtures/*.json`
  and example IR loads in both languages; every `fixtures/invalid/*.json` is
  rejected by Python, and by TS unless it is one of the documented Python-only
  semantic cases (duplicate id, dangling ref, keyboard bounds).

## Bridge

`python/bridge.py` is a stdlib-only JSON-lines bridge. One
`uv run --package atomc-core-ir python bridge.py` process is spawned per test file
and multiplexes requests over stdin/stdout by id:

- `{"id":1,"op":"validate","ir":{...}}` → `{"id":1,"ok":true,"ir":{...},"canonical":"..."}`
- `{"id":2,"op":"patch","ir":{...},"path":"/electrical","base_rev":2,"ops":[...],"holder":"..."}`
  → `{"id":2,"ok":true,"ir":{...},"canonical":"...","new_rev":3,"changed_paths":[...]}`
- failures → `{"id":2,"ok":false,"error":{"type":"conflict|locked|validation|ref_integrity|patch","message":"..."}}`

The process exits non-zero if any request failed, so it is also usable as a
single-shot CLI. Set `ATOMC_BRIDGE_TIMEOUT_MS` to override the per-request timeout.

## Commands (from repo root)

```bash
pnpm install --frozen-lockfile
pnpm --filter @atomc/contract-tests contract
pnpm --filter @atomc/contract-tests test
pnpm --filter @atomc/contract-tests typecheck
pnpm --filter @atomc/contract-tests lint
pnpm exec turbo run contract
```

`contract` and `test` are the same Vitest run; `turbo run contract` discovers this
package through its `contract` script. No daemon, network, LLM, or hardware is
required — only `uv` (Python 3.14) and pnpm.
