# WP-1.3 `contract-tests` — handoff

Branch: `wp/1.3-contract-tests` · Status: **done, green** · Depends on: WP-1.1 (`atomc-core-ir`),
WP-1.2 (`@atomc/core-ir`), WP-1.4 CI.

## What was built

A private pnpm workspace package **`@atomc/contract-tests`** at `tests/contract/` that drives the real
Python models and the real generated TypeScript types/zod schemas against each other. No daemon,
network, LLM, or hardware.

- `tests/contract/package.json` — ESM, `contract`/`test`/`typecheck`/`lint` scripts, deps
  `@atomc/core-ir: workspace:*` (runtime) + catalog `vitest`, `typescript`, `@types/node`, `vite`.
- `tests/contract/python/bridge.py` — stdlib-only JSON-lines bridge. Ops: `validate`
  (`SystemIR.load` → canonical `dump()`) and `patch` (`apply_patch` → updated IR + `new_rev` +
  `changed_paths`). Structured errors `{type: conflict|locked|validation|ref_integrity|patch|error,
  message}`; the process exits non-zero if any request failed. Ops are **relative to `path`** per
  ir-schema.md §2.
- `tests/contract/ts/helpers/bridge.ts` — spawns **one** `uv run --package atomc-core-ir python
  bridge.py` process per test file, multiplexes requests by id, enforces a per-request timeout
  (`ATOMC_BRIDGE_TIMEOUT_MS`, default 300 s) and surfaces stdout/stderr on failure. Uses argv (spaces
  in paths are safe) and `cwd` = repo root.
- `tests/contract/ts/helpers/python.ts` — `pythonCanonical(path)` runs
  `uv run --package atomc-core-ir python -c ...` via `execFile` (argv, no shell).
- `tests/contract/ts/roundtrip.test.ts` — Py→TS and TS→Py round-trips for both example IRs.
- `tests/contract/ts/patches.test.ts` — RFC 6902 transactions against `/electrical/assertions` with
  `base_rev` = `electrical._meta.rev`.
- `tests/contract/ts/fixtures.test.ts` — valid fixtures load in both languages; invalid fixtures are
  rejected by Python and by TS unless they are documented Python-only semantic cases.
- `tests/contract/README.md` — protocol and exact commands.

## Coverage (30 Vitest tests)

- **Round-trip** (4): for `examples/atomc-pad` and `examples/atomc-keeb` —
  (a) Python canonical JSON accepted by TS `parseSystemIR()` and its normalized shape equals parsing
  the source fixture; (b) TS zod-normalized serialization accepted by Python `SystemIR.load()`, and
  Python's `dump()` re-accepted by TS.
- **Patches** (12): for each example — `replace` (`/assertions/0/status` → `fail`), `add`
  (`/assertions/-` new valid assertion), `remove` (`/assertions/0`), invalid enum value rolls back
  (`validation`, and a subsequent valid patch on the same `base_rev` still returns rev + 1), stale
  `base_rev` → `conflict`, and an injected future lock by another holder → `locked`. Asserts
  `new_rev == doc rev + 1`, node `_meta.rev == new_rev`, and
  `changed_paths == ["/electrical/assertions/0/status"]`.
- **Fixtures** (14): `packages/core-ir/fixtures/{minimal,atomc-pad}.json` + both example IRs load in
  TS and Python; all 5 `fixtures/invalid/*.json` are rejected in Python (`ref_integrity` for
  dangling_ref/duplicate_id, `validation` for bad_unit_type/extra_key/keyboard_row_out_of_range), and
  in TS either rejected structurally or classified as a documented Python-only case.

## How to verify (exact commands, from repo root)

```bash
pnpm install --frozen-lockfile
pnpm --filter @atomc/contract-tests contract   # 30 passed
pnpm --filter @atomc/contract-tests test       # same Vitest run
pnpm --filter @atomc/contract-tests typecheck
pnpm --filter @atomc/contract-tests lint
pnpm exec turbo run contract                   # builds @atomc/core-ir, then runs contract
uv run pytest packages/core-ir/python -q       # 56 passed
uv run ruff check tests/contract/python
uv run ruff format --check tests/contract/python
uv run mypy tests/contract/python              # strict, clean
pnpm exec biome check tests/contract
```

All green locally (macOS arm64, CPython 3.14, Node 25).

## Design decisions

- **One bridge process per test file** (spawned in `beforeAll`, killed in `afterAll`), multiplexed by
  request id over newline-delimited JSON. Keeps the uv-startup cost to a single spawn per file while
  giving per-request structured errors. The bridge also works single-shot (one request, non-zero exit
  on error).
- **Ops are relative to `path`.** `apply_patch` resolves `path` to a subtree and applies ops relative
  to it (ir-schema.md §2). Therefore the tests build ops with `patch()` (empty base) and pointers like
  `/assertions/0/status`, passing `path: "/electrical"`. `changed_paths` still comes back as
  `/electrical/assertions/0/status`. (Using `patch("/electrical")` would double-prefix and is the
  documented TS-builder convenience for absolute pointers only — noted for WP-1.2/daemon alignment.)
- **`/electrical/assertions`** is the shared patch target: both examples have it and it is referenced
  by nothing, so replace/add/remove are safe. The keeb has no sourcing BOM, so sourcing was avoided.
- **Lock test without a lock op**: inject a future-dated lock into `electrical._meta.lock` and patch
  as a different holder. The brief's bridge surface (`validate`/`patch`) is unchanged.
- **No external runtime deps**: only the workspace `@atomc/core-ir` plus catalog dev tooling.

## Deviations from contract

None. The bridge and tests follow ir-schema.md §2 transaction semantics (relative ops, `base_rev` =
owning top-level node rev, pure rollback, structured conflict/locked errors).

## Root changes needed

- **`pnpm-lock.yaml`** — minimal, additive: exactly one new importer (`tests/contract`) linking
  `@atomc/core-ir` (workspace) and catalog `@types/node`, `typescript`, `vite`, `vitest`. No new
  package resolutions, no catalog changes, no unrelated edits. Confirmed by
  `pnpm install --frozen-lockfile`. (Orchestrator pre-approved this lockfile update.)
- No other root files touched. No CI change needed: `ci.yml`'s `contract` job already runs
  `pnpm exec turbo run contract`, which now discovers this package.

## Open issues

- The TS `patch(base)` builder emits **absolute** pointers while `apply_patch` expects ops **relative**
  to `path`. The contract freezes the Python semantics; tests therefore use `patch()` with empty base.
  When the daemon RPC lands (Phase 2), align the TS client so it either strips the base or the Python
  side accepts absolute pointers — flag for WP-2.5/WP-2.6.
- Zod validates `date-time` as a plain string (shape-only); the lock test relies on Python's stricter
  timestamp parsing for `expires_at`, which is fine since Python is the applying side.
- Bridge timeouts are generous (300 s) because the first `uv run` may sync; CI warms nothing, so the
  contract job's wall time is dominated by `uv run` startup (~1 s here).
