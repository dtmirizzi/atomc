# WP-1.1 `core-ir-py` — Pydantic v2 models for system_ir.json

Read `_common.md` first. Contract: `docs/architecture/contracts/ir-schema.md` (implement it exactly)
and `gate-result.md` (the GateResult model lives in core-ir).

## Owned paths
`packages/core-ir/python/**`, `packages/core-ir/schema/**`, `packages/core-ir/fixtures/**`,
`packages/core-ir/README.md`.

## Deliverables
1. Distribution `atomc-core-ir` at `packages/core-ir/python/pyproject.toml`, import name `atomc_core_ir`,
   `src/` layout, deps: `pydantic>=2.14`, `jsonpatch` (or a small in-house RFC 6902 impl — your call,
   justify in handoff), `py.typed`.
2. Modules: `common.py` (ID/Ref/units/Artifact/NodeMeta/Lock types), one module per domain node
   (`electrical.py`, `layout.py`, `keyboard.py`, `firmware.py`, `simulation.py`, `mechanical.py`,
   `sourcing.py`, `fabrication.py`, `orders.py`, `gates.py`, `provenance.py`), `document.py`
   (`SystemIR`), `tx.py` (apply_patch, locks, errors), `schema.py` (export), `__init__.py` re-exports
   the public API from contract §5.
3. Referential integrity validator on `SystemIR` (every `*_ref`/`*_refs` resolves; ids unique).
   Keyboard validators from contract §4.3.
4. `python -m atomc_core_ir.schema > packages/core-ir/schema/system_ir.schema.json` — commit the file.
   Add a `--check` flag that exits 1 if the committed file differs (used by CI).
5. Fixtures in `packages/core-ir/fixtures/`: `minimal.json` (meta only), `atomc-pad.json` — a realistic
   3×3 macropad on STM32F411CEU6: components (U1 MCU, J1 USB-C, U2 LDO, U3 USBLC6, R1/R2 5.1k CC,
   SW1-9 + D1-9, C*), nets, layout with outline 80×80 mm, placements, ≥12 bottom test pads (VBUS, 3V3,
   GND, SWDIO, SWCLK, NRST, BOOT0, UART TX/RX, ROW0-2, COL0-2), 4 mounting holes, keyboard node with
   matrix rows B12,B13,B14 / cols A8,A9,A10 (just an example — keep it consistent), keys, usb, qmk;
   firmware target with memory map; a few sourcing lines with offers; one GateResult. Plus
   `invalid/*.json` negative fixtures (dangling ref, duplicate id, bad unit type, extra key,
   keyboard row out of range) — each must fail validation with a clear message.
6. Tests (`packages/core-ir/python/tests/`): load/dump round-trip byte-stability on every fixture;
   negative fixtures; hypothesis strategies generating valid SystemIR instances (put strategies in
   `atomc_core_ir.testing` so other packages reuse them) → round-trip; tx tests: conflict, lock held,
   lock expired, invalid patch rolls back, rev bookkeeping; schema-drift test. Coverage ≥ 90 %.

## Definition of done
`uv run --package atomc-core-ir pytest packages/core-ir/python --cov=atomc_core_ir --cov-fail-under=90`,
ruff + mypy --strict clean, schema committed, handoff written, branch pushed.
Commit the schema file EARLY (as soon as models compile) and push, because WP-1.2 generates TS from it;
then keep iterating.
