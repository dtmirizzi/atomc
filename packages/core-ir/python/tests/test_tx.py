"""Transaction (apply_patch) and lock semantics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from atomc_core_ir import (
    ConflictError,
    LockedError,
    PatchError,
    SystemIR,
    acquire_lock,
    apply_patch,
    release_lock,
)
from pydantic import ValidationError

FIXTURES = __import__("pathlib").Path(__file__).resolve().parents[2] / "fixtures"
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _pad() -> SystemIR:
    return SystemIR.load(FIXTURES / "atomc-pad.json")


def _replace_value(value: object, path: str = "/build_qty") -> dict[str, Any]:
    return {"op": "replace", "path": path, "value": value}


def test_apply_patch_bumps_revisions_and_is_pure() -> None:
    ir = _pad()
    assert ir.sourcing is not None
    base = ir.sourcing.meta_.rev
    new, result = apply_patch(ir, "/sourcing", base, [_replace_value(9)])
    assert new.sourcing is not None
    assert new.sourcing.build_qty == 9
    assert result.new_rev == ir.meta.rev + 1
    assert new.meta.rev == result.new_rev
    assert new.sourcing.meta_.rev == result.new_rev
    assert result.changed_paths == ["/sourcing/build_qty"]
    assert ir.sourcing.build_qty == 5  # input unchanged


def test_apply_patch_nested_subtree() -> None:
    ir = _pad()
    assert ir.electrical is not None
    base = ir.electrical.meta_.rev
    new, _ = apply_patch(ir, "/electrical/components/4", base, [_replace_value("10k", "/value")])
    assert new.electrical is not None
    assert new.electrical.components[4].value == "10k"
    assert ir.electrical.components[4].value == "5.1k"


def test_apply_patch_op_types_add_copy_move_remove_test() -> None:
    ir = _pad()
    assert ir.electrical is not None
    base = ir.electrical.meta_.rev
    ops = [
        {"op": "add", "path": "/a", "value": "1"},
        {"op": "copy", "from": "/a", "path": "/b"},
        {"op": "move", "from": "/b", "path": "/c"},
        {"op": "test", "path": "/c", "value": "1"},
        {"op": "remove", "path": "/c"},
    ]
    new, _ = apply_patch(ir, "/electrical/components/0/attributes", base, ops)
    assert new.electrical is not None
    assert new.electrical.components[0].attributes == {"a": "1"}


def test_apply_patch_list_append() -> None:
    ir = _pad()
    assert ir.sourcing is not None
    base = ir.sourcing.meta_.rev
    line = {"id": "bom:C99", "qty_per_unit": 1}
    new, _ = apply_patch(ir, "/sourcing/bom", base, [{"op": "add", "path": "/-", "value": line}])
    assert new.sourcing is not None
    assert new.sourcing.bom[-1].id == "bom:C99"


def test_apply_patch_conflict() -> None:
    ir = _pad()
    assert ir.sourcing is not None
    base = ir.sourcing.meta_.rev
    with pytest.raises(ConflictError) as excinfo:
        apply_patch(ir, "/sourcing", base + 1, [_replace_value(9)])
    assert excinfo.value.current_rev == base


def test_apply_patch_invalid_patch_rolls_back() -> None:
    ir = _pad()
    assert ir.sourcing is not None
    base = ir.sourcing.meta_.rev
    with pytest.raises(PatchError):
        apply_patch(ir, "/sourcing", base, [{"op": "test", "path": "/build_qty", "value": 999}])
    with pytest.raises(PatchError):
        apply_patch(ir, "/sourcing", base, [{"op": "remove", "path": "/nope"}])
    with pytest.raises(PatchError):
        apply_patch(ir, "/sourcing", base, [{"op": "frobnicate", "path": "/x"}])
    with pytest.raises(PatchError):
        apply_patch(ir, "/sourcing", base, [{"op": "add", "path": "/x"}])
    assert ir.sourcing.build_qty == 5


def test_apply_patch_invalid_result_rejected() -> None:
    ir = _pad()
    assert ir.sourcing is not None
    base = ir.sourcing.meta_.rev
    with pytest.raises(ValidationError):
        apply_patch(ir, "/sourcing", base, [_replace_value("not-an-int")])


def test_apply_patch_unknown_node() -> None:
    ir = _pad()
    with pytest.raises(PatchError):
        apply_patch(ir, "/nope", 0, [{"op": "add", "path": "/x", "value": 1}])


def test_apply_patch_creates_node_from_null() -> None:
    ir = SystemIR.load(FIXTURES / "minimal.json")
    assert ir.sourcing is None
    new, result = apply_patch(
        ir, "/sourcing", 0, [{"op": "replace", "path": "", "value": {"build_qty": 7}}]
    )
    assert new.sourcing is not None
    assert new.sourcing.build_qty == 7
    assert new.sourcing.meta_.rev == result.new_rev == new.meta.rev


def test_apply_patch_whole_document() -> None:
    ir = _pad()
    _new, result = apply_patch(
        ir, "", ir.meta.rev, [{"op": "test", "path": "/meta/name", "value": "atomc-pad"}]
    )
    assert result.changed_paths == ["/meta/name"]


def test_apply_patch_error_branches() -> None:
    ir = _pad()
    assert ir.sourcing is not None
    base = ir.sourcing.meta_.rev
    failed_ops: list[list[dict[str, Any]]] = [
        [{"op": "remove", "path": ""}],
        [{"op": "remove", "path": "/bom/xx"}],
        [{"op": "add", "path": "/bom/xx", "value": 1}],
        [{"op": "replace", "path": "/bom/9", "value": 1}],
        [{"op": "remove", "path": "/build_qty/x"}],
    ]
    for ops in failed_ops:
        with pytest.raises(PatchError):
            apply_patch(ir, "/sourcing", base, ops)


def test_apply_patch_document_meta_subtree() -> None:
    ir = _pad()
    new, result = apply_patch(
        ir, "/meta", ir.meta.rev, [{"op": "replace", "path": "/name", "value": "renamed"}]
    )
    assert new.meta.name == "renamed"
    assert result.new_rev == ir.meta.rev + 1


def test_apply_patch_root_add() -> None:
    ir = _pad()
    assert ir.sourcing is not None
    base = ir.sourcing.meta_.rev
    value = ir.sourcing.model_dump(mode="json", by_alias=True)
    new, _ = apply_patch(ir, "/sourcing", base, [{"op": "add", "path": "", "value": value}])
    assert new.sourcing is not None
    assert new.sourcing.build_qty == 5


def test_release_lock_missing_node() -> None:
    minimal = SystemIR.load(FIXTURES / "minimal.json")
    with pytest.raises(ValueError, match="cannot unlock missing node"):
        release_lock(minimal, "sourcing", "agent:a")


def test_conflict_for_absent_node() -> None:
    minimal = SystemIR.load(FIXTURES / "minimal.json")
    with pytest.raises(ConflictError) as excinfo:
        apply_patch(minimal, "/sourcing", 5, [{"op": "replace", "path": "", "value": {}}])
    assert excinfo.value.current_rev == 0


def test_acquire_and_release_lock() -> None:
    ir = _pad()
    locked = acquire_lock(ir, "sourcing", "agent:ee-agent#1", 60, reason="swap", now=T0)
    assert locked.sourcing is not None
    assert locked.sourcing.meta_.lock is not None
    assert locked.sourcing.meta_.lock.holder == "agent:ee-agent#1"
    assert locked.meta.rev == ir.meta.rev  # locking does not bump rev

    released = release_lock(locked, "sourcing", "agent:ee-agent#1", now=T0)
    assert released.sourcing is not None
    assert released.sourcing.meta_.lock is None
    # releasing an unlocked node is a no-op
    assert release_lock(ir, "sourcing", "agent:ee-agent#1", now=T0) is ir


def test_apply_patch_blocked_by_lock() -> None:
    ir = _pad()
    locked = acquire_lock(ir, "sourcing", "agent:a", 60, now=T0)
    assert locked.sourcing is not None
    base = locked.sourcing.meta_.rev
    with pytest.raises(LockedError) as excinfo:
        apply_patch(locked, "/sourcing", base, [_replace_value(9)], holder="agent:b", now=T0)
    assert excinfo.value.holder == "agent:a"
    # the lock holder may proceed
    new, _ = apply_patch(locked, "/sourcing", base, [_replace_value(9)], holder="agent:a", now=T0)
    assert new.sourcing is not None
    assert new.sourcing.build_qty == 9


def test_expired_lock_does_not_block() -> None:
    ir = _pad()
    locked = acquire_lock(ir, "sourcing", "agent:a", 10, now=T0)
    assert locked.sourcing is not None
    base = locked.sourcing.meta_.rev
    later = T0 + timedelta(seconds=20)
    new, _ = apply_patch(
        locked, "/sourcing", base, [_replace_value(9)], holder="agent:b", now=later
    )
    assert new.sourcing is not None
    assert new.sourcing.build_qty == 9


def test_lock_contention_and_refresh() -> None:
    ir = _pad()
    first = acquire_lock(ir, "sourcing", "agent:a", 10, now=T0)
    # same holder may refresh
    second = acquire_lock(first, "sourcing", "agent:a", 100, now=T0)
    assert second.sourcing is not None
    assert second.sourcing.meta_.lock is not None
    with pytest.raises(LockedError):
        acquire_lock(second, "sourcing", "agent:b", 10, now=T0)
    # another holder may take over an expired lock
    later = T0 + timedelta(seconds=200)
    third = acquire_lock(second, "sourcing", "agent:b", 10, now=later)
    assert third.sourcing is not None
    assert third.sourcing.meta_.lock is not None
    assert third.sourcing.meta_.lock.holder == "agent:b"


def test_release_lock_by_other_holder_rejected() -> None:
    ir = _pad()
    locked = acquire_lock(ir, "sourcing", "agent:a", 60, now=T0)
    with pytest.raises(LockedError):
        release_lock(locked, "sourcing", "agent:b", now=T0)


def test_lock_invalid_targets() -> None:
    ir = _pad()
    with pytest.raises(ValueError, match="not a lockable"):
        acquire_lock(ir, "meta", "agent:a", 10)
    minimal = SystemIR.load(FIXTURES / "minimal.json")
    with pytest.raises(ValueError, match="cannot lock missing node"):
        acquire_lock(minimal, "sourcing", "agent:a", 10)
    with pytest.raises(ValueError, match="must not be empty"):
        acquire_lock(minimal, "", "agent:a", 10)
