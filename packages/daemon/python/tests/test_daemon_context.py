"""PluginContext: IR access and contained artifact paths."""

from __future__ import annotations

from pathlib import Path

import pytest
from atomcd.ir_store import IRStore
from atomcd.plugins.context import PluginContext, ScopeError


def make_context(tmp_path: Path) -> PluginContext:
    store = IRStore(tmp_path)
    store.load()
    return PluginContext(
        plugin_name="demo",
        holder="plugin:demo",
        store=store,
        produces=["/sourcing"],
        artifact_root=tmp_path / "artifacts" / "demo",
        cache={},
    )


async def test_ir_get_root(tmp_path: Path) -> None:
    ctx = make_context(tmp_path)
    value = await ctx.ir_get("/")
    assert value["schema_version"] == "0.1.0"


async def test_ir_read_reports_rev(tmp_path: Path) -> None:
    ctx = make_context(tmp_path)
    read = await ctx.ir_read("/")
    assert read["rev"] == 0
    assert read["value"]["meta"]["rev"] == 0


def test_artifact_path_contained(tmp_path: Path) -> None:
    ctx = make_context(tmp_path)
    assert ctx.artifact_path("reports", "bom.csv") == (
        tmp_path / "artifacts" / "demo" / "reports" / "bom.csv"
    )


def test_artifact_path_rejects_traversal(tmp_path: Path) -> None:
    ctx = make_context(tmp_path)
    with pytest.raises(ScopeError):
        ctx.artifact_path("../escape")
    with pytest.raises(ScopeError):
        ctx.artifact_path("/absolute")
