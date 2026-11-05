# WP-1.3 `contract-tests` — cross-language IR conformance

Read `_common.md` first. Read `docs/architecture/contracts/ir-schema.md` in full, especially §§1–2,
5–6; use `docs/architecture/contracts/rpc.md` only as context (daemon RPC is not implemented yet).
WP-1.1 Python models and WP-1.2 TS generated types/helpers are already merged to `main`; both examples
and their committed `system_ir.json` files are available.

## Owned paths
- `tests/contract/**`
- `docs/plan/handoffs/WP-1.3.md`

Do not edit `.github/workflows/**`, `turbo.json`, root `package.json`, `pnpm-workspace.yaml`, or either
core-ir package. If CI wiring or root workspace changes are necessary, report them under "Root changes
needed" in the handoff; the existing CI workflow already runs `pnpm exec turbo run contract` if this
package exists.

## Deliverables
1. A private TypeScript workspace package `@atomc/contract-tests` in `tests/contract/package.json`
   (ESM, latest catalog versions only, Vitest). Add `contract` and `test` scripts; Turbo's existing
   `contract` task will discover it. Keep runtime dependencies empty where possible.
2. Cross-language round-trip suite under `tests/contract/ts/` using Vitest:
   - Python emits canonical JSON for both `examples/atomc-pad/system_ir.json` and
     `examples/atomc-keeb/system_ir.json` via `uv run --package atomc-core-ir python -c ...`; TS loads
     stdout and `parseSystemIR()` accepts it. Compare parsed canonical shape to source fixture.
   - TS loads each example fixture, validates with zod, serializes it, and Python
     `SystemIR.load(json_bytes)` accepts it; Python emits `dump()` and TS parses that output.
   - For both examples, TS produces RFC 6902 patches using `patch()`; Python applies them using
     `apply_patch` and reports the new revision/value. Cover `replace`, `add`, `remove`, an optimistic
     revision conflict (stale `base_rev`), and an invalid patch that must roll back. The transaction
     base is the correct top-level node `_meta.rev`; check values against expected outputs.
   - Verify all `packages/core-ir/fixtures/*.json` validate in TS and Python. Verify every
     `packages/core-ir/fixtures/invalid/*.json` is rejected in Python. For TS, structural-invalid
     files must be rejected; explicitly skip the Python-only semantic cases (dangling ref, duplicate
     id, keyboard bounds) per WP-1.2 handoff, and assert that each accepted file is classified as one
     of those cases (do not silently accept arbitrary failures).
3. A small stdlib Python JSON-lines bridge in `tests/contract/python/bridge.py` with operations:
   `validate` (read JSON stdin, `SystemIR.load`, output canonical JSON or structured error),
   `patch` (read `{ir,path,base_rev,ops,holder}`, call `apply_patch`, output updated IR and `new_rev`;
   return structured conflict/locked/validation errors and nonzero exit on error). No daemon needed.
4. Deterministic tests only: no LLM, vendor network, or hardware kernels. Spawn subprocesses with
   `uv run --package atomc-core-ir python <bridge.py>` (use repo-root cwd; respect paths containing
   spaces; enforce timeout). Tests must fail with useful stdout/stderr context if the bridge fails.
5. Package README with exact root commands. Update only its owned paths.

## Definition of done
From repo root:

```bash
pnpm install --frozen-lockfile
pnpm --filter @atomc/contract-tests contract
pnpm --filter @atomc/contract-tests test
pnpm exec turbo run contract
uv run pytest packages/core-ir/python -q
```

All green. Confirm `pnpm-lock.yaml` is unchanged (no dependencies expected); if workspace importers
require a lockfile change, ask the orchestrator before editing. Write handoff with concrete coverage,
commands, known gaps, and any root changes needed; commit and push branch `wp/1.3-contract-tests`.
