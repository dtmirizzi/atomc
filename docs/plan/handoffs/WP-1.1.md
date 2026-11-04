# WP-1.1 handoff — `core-ir-py`

Branch: `wp/1.1-core-ir-py` · Status: **done, green** · Depends on: WP-1.0 contracts

## What was built

Distribution `atomc-core-ir` at `packages/core-ir/python/` (src layout, hatchling, `py.typed`),
import name `atomc_core_ir`. Implements `docs/architecture/contracts/ir-schema.md` exactly and
`gate-result.md` for `GateResult`.

- **Models** (`common.py` + one module per §4 node): `electrical`, `layout`, `keyboard`,
  `firmware`, `simulation`, `mechanical`, `sourcing`, `fabrication`, `orders`, `gates`,
  `provenance`, plus `document.py` (`SystemIR`, `DocumentMeta`).
- **Global conventions**: `snake_case` JSON, `extra="forbid"` on every model (except `ext`
  dicts), unit-annotated aliases (`LengthMm`, `AngleDeg`, …), `<kind>:<slug>` id validator,
  RFC 3339 UTC timestamps serialised with a trailing `Z`, `sha256:<hex>` validation,
  per-node `_meta` envelope (`meta_` field aliased to `_meta`).
- **API** (§5): `SystemIR.load/dump/empty`, `export_json_schema()`, `apply_patch`,
  `acquire_lock`, `release_lock`, `ConflictError`, `LockedError` (+ `PatchError`), `RefIntegrityError`.
  All pure — the daemon owns persistence.
- **Canonical form**: `json.dumps(model_dump(mode="json", by_alias=True, exclude_none=True),
  sort_keys=True, indent=2) + "\n"`, so `dump()` is byte-stable and diff-friendly.
- **Transactions**: in-house RFC 6902 (add/remove/replace/move/copy/test), optimistic
  `base_rev` conflict detection, unexpired-lock rejection (same holder may proceed), document
  rev + node `_meta.rev` bookkeeping, full re-validation + referential integrity *before*
  returning (failed patches leave the input untouched).
- **Referential integrity**: `SystemIR.validate_refs()` checks document-wide id uniqueness and
  that every `*_ref`/`*_refs` (pins, placements, test pads, keys, signals, bboxes, BOM lines,
  chosen offers, captures, gate refs/evidence) resolves.
- **Keyboard validators** (§4.3): `(row, col)` unique, `row < rows`, `col < cols`,
  `len(row_pins) == rows`, `len(col_pins) == cols`.
- **Schema**: committed at `packages/core-ir/schema/system_ir.schema.json` (3003 lines) with a
  `--check` drift flag.
- **Fixtures**: `fixtures/minimal.json`, `fixtures/atomc-pad.json` (real 3×3 macropad on
  STM32F411CEU6: 27 components, 19 nets, 15 bottom test pads, 4 mounting holes, 3×3 matrix +
  keys, firmware target/peripherals/suite, simulation, sourcing offers, one `GateResult`,
  provenance) and 5 negative fixtures in `fixtures/invalid/`.
- **Tests**: 56 tests — byte-stable round-trip on both valid fixtures, all 5 invalid fixtures,
  model validators, tx/lock semantics, schema drift, and Hypothesis property tests using the
  reusable `atomc_core_ir.testing.system_ir_strategy()`. Coverage **98.0 %**.

## How to verify (exact commands)

```bash
cd <worktree>
uv sync --all-packages

uv run --package atomc-core-ir pytest packages/core-ir/python \
  --cov=atomc_core_ir --cov-fail-under=90

uv run ruff check packages/core-ir/python
uv run ruff format --check packages/core-ir/python
uv run mypy packages/core-ir/python

uv run --package atomc-core-ir python -m atomc_core_ir.schema --check
```

All pass locally (macOS, CPython 3.14.0).

## Design decisions

- **In-house RFC 6902** instead of the `jsonpatch` dependency: keeps the only runtime dependency
  at Pydantic (PLAN §2), gives full control over root-level/pointer semantics and error types,
  and avoids adding a dependency to the shared `uv.lock`.
- **`strict=True` not enabled globally.** The brief says "strict mode"; the authoritative
  contract (§1) specifies `extra="forbid"` as the strictness rule. Pydantic `strict=True` would
  reject RFC 3339 datetime *strings* and JSON arrays for tuple fields, i.e. it would make
  `load()` of any real `system_ir.json` impossible without bespoke before-validators. We honour
  `extra="forbid"` + constrained types + validators instead (documented here as the one
  interpretation call).
- **`exclude_none=True`** in canonical dumps so omitted optionals stay omitted; committed
  fixtures are regenerated into this canonical form so round-trips are byte-exact.
- **`_meta` required** on every top-level domain node (per contract); `apply_patch` injects a
  default `{rev, lock}` envelope when creating a node from `null`.
- **Locks do not bump `rev`** (rev tracks data changes only); locking/unlocking still
  re-validates and returns a new document.
- **Polygons** are implicitly closed (`>= 3` points); an explicit repeated first vertex is also
  accepted. (The contract's "closed" wording was read as "a closed ring".)
- **`export_json_schema` lives in `document.py`** (re-exported from `__init__`) so
  `python -m atomc_core_ir.schema` does not pre-import the module and emit a runpy warning.

## Deviations from contract

None in the schema surface. Interpretation notes above: global pydantic `strict=True` not used
(contract only mandates `extra="forbid"`), and polygon closure is implicit.

## Root changes needed

- `uv.lock` was updated by `uv sync --all-packages` (adds `pydantic`, `pydantic-core`,
  `annotated-types`, `typing-inspection`, `typing-extensions` and the `atomc-core-ir` workspace
  member). This is a root file; included in the commit because the package cannot build without
  it — orchestrator should expect it and re-lock after other Python WPs land.
- No edits to other root files (`pyproject.toml`, `pnpm-workspace.yaml`, `turbo.json`,
  `biome.json`, `tsconfig.base.json`, `.github/**`).

## Open issues

- `uv run --package atomc-core-ir pytest` prints a pytest-asyncio deprecation warning about
  `asyncio_default_fixture_loop_scope` (root `pyproject.toml` config). Harmless; root-owned.
- `testing.py` has one uncovered line (a rare Hypothesis branch) — not worth forcing.
- WP-1.2 generates TS from the committed schema; that file is pushed on this branch already.
