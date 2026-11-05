"""IRStore: persistence, revisions, locks, validation and concurrency."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from atomc_core_ir import ConflictError, LockedError, SystemIR
from atomcd.ir_store import IR_FILENAME, IRStore, MissingNodeError
from pydantic import ValidationError

ELECTRICAL_NODE: dict[str, Any] = {
    "_meta": {"rev": 0, "lock": None},
    "source": {"kind": "atopile", "entry": "main.ato:App"},
    "components": [],
    "nets": [],
    "assertions": [],
    "erc": [],
}


def add_electrical(base_rev: int = 0) -> list[dict[str, Any]]:
    return [{"op": "add", "path": "", "value": ELECTRICAL_NODE}]


def test_load_creates_file(project_root: Path) -> None:
    store = IRStore(project_root)
    ir = store.load()
    assert ir.meta.rev == 0
    assert (project_root / IR_FILENAME).exists()
    assert ir.meta.project_id == f"proj:{project_root.name}"


def test_load_roundtrip(project_root: Path) -> None:
    IRStore(project_root).load()
    reloaded = IRStore(project_root).load()
    assert isinstance(reloaded, SystemIR)
    assert reloaded.meta.rev == 0


def test_read_root_and_missing(project_root: Path) -> None:
    store = IRStore(project_root)
    store.load()
    rev, value = store.read("/")
    assert rev == 0
    assert value["schema_version"] == "0.1.0"
    with pytest.raises(MissingNodeError):
        store.read("/mechanical")


async def test_transact_persists(project_root: Path) -> None:
    store = IRStore(project_root)
    store.load()
    result = await store.transact("/electrical", 0, add_electrical())
    assert result.new_rev == 1
    assert result.changed_paths == ["/electrical"]
    assert store.read("/electrical")[0] == 1
    on_disk = SystemIR.load(project_root / IR_FILENAME)
    assert on_disk.meta.rev == 1
    assert on_disk.electrical is not None


async def test_stale_conflict_leaves_state(project_root: Path) -> None:
    store = IRStore(project_root)
    store.load()
    await store.transact("/electrical", 0, add_electrical())
    before = (project_root / IR_FILENAME).read_text(encoding="utf-8")
    with pytest.raises(ConflictError) as exc_info:
        await store.transact("/electrical", 0, add_electrical())
    assert exc_info.value.current_rev == 1
    assert (project_root / IR_FILENAME).read_text(encoding="utf-8") == before


async def test_invalid_patch_leaves_state(project_root: Path) -> None:
    store = IRStore(project_root)
    store.load()
    bad = [{"op": "add", "path": "", "value": {"source": {"kind": "nope"}}}]
    before = store.rev
    with pytest.raises(ValidationError):
        await store.transact("/electrical", 0, bad)
    assert store.rev == before
    assert store.read("/")[0] == 0


async def test_lock_blocks_other_holder(project_root: Path) -> None:
    store = IRStore(project_root)
    store.load()
    await store.transact("/electrical", 0, add_electrical())
    await store.lock("/electrical", "agent:a", 60)
    with pytest.raises(LockedError):
        await store.transact(
            "/electrical",
            1,
            [{"op": "replace", "path": "/source/entry", "value": "x.ato:App"}],
            holder="agent:b",
        )
    # Same holder may still write.
    result = await store.transact(
        "/electrical",
        1,
        [{"op": "replace", "path": "/source/entry", "value": "x.ato:App"}],
        holder="agent:a",
    )
    assert result.new_rev == 2
    assert await store.unlock("/electrical", "agent:a") is True


async def test_locked_node_reports_holder(project_root: Path) -> None:
    store = IRStore(project_root)
    store.load()
    await store.transact("/electrical", 0, add_electrical())
    expires = await store.lock("/electrical", "agent:a", 60, reason="swap")
    from datetime import UTC, datetime

    assert datetime.fromisoformat(expires.replace("Z", "+00:00")) > datetime.now(UTC)


async def test_parallel_transactions_only_one_base_rev_wins(project_root: Path) -> None:
    store = IRStore(project_root)
    store.load()

    async def attempt() -> str:
        try:
            await store.transact("/electrical", 0, add_electrical())
        except ConflictError:
            return "conflict"
        return "ok"

    outcomes = await asyncio.gather(*(attempt() for _ in range(8)))
    assert outcomes.count("ok") == 1
    assert outcomes.count("conflict") == 7
    assert store.rev == 1
