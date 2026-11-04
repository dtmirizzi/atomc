"""Hypothesis round-trip, integrity and transaction properties."""

from __future__ import annotations

from atomc_core_ir import SystemIR, apply_patch
from atomc_core_ir.testing import system_ir_strategy
from hypothesis import given, settings

SETTINGS = settings(max_examples=25, deadline=None)


@SETTINGS
@given(system_ir_strategy())
def test_generated_documents_roundtrip(ir: SystemIR) -> None:
    text = ir.dump()
    assert SystemIR.load(text).dump() == text


@SETTINGS
@given(system_ir_strategy())
def test_generated_documents_are_referentially_closed(ir: SystemIR) -> None:
    ir.validate_refs()


@SETTINGS
@given(system_ir_strategy())
def test_transaction_increments_rev(ir: SystemIR) -> None:
    assert ir.sourcing is not None
    base = ir.sourcing.meta_.rev
    new, result = apply_patch(
        ir, "/sourcing", base, [{"op": "replace", "path": "/build_qty", "value": 42}]
    )
    assert result.new_rev == ir.meta.rev + 1
    assert new.meta.rev == result.new_rev
    assert new.sourcing is not None
    assert new.sourcing.meta_.rev == result.new_rev
    assert new.sourcing.build_qty == 42
