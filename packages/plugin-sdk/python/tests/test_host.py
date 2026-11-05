"""The fake host and the PluginHost structural protocol."""

from __future__ import annotations

from pathlib import Path

import pytest
from atomc_plugin_sdk.host import IrSnapshot, PluginHost, TransactResult
from atomc_plugin_sdk.testing import FakePluginHost


def test_fake_host_satisfies_protocol(tmp_path: Path) -> None:
    host = FakePluginHost(root=tmp_path)
    assert isinstance(host, PluginHost)


def test_ir_get_returns_revision(tmp_path: Path) -> None:
    host = FakePluginHost(root=tmp_path, ir={"sourcing": {}}, rev=3)
    snapshot = host.ir_get("/sourcing")
    assert isinstance(snapshot, IrSnapshot)
    assert snapshot.rev == 3
    assert snapshot.value == {"sourcing": {}}


def test_ir_transact_records_and_bumps(tmp_path: Path) -> None:
    host = FakePluginHost(root=tmp_path, rev=1)
    result = host.ir_transact(
        "/sourcing", 1, [{"op": "add", "path": "/bom", "value": []}], holder="ops-agent"
    )
    assert isinstance(result, TransactResult)
    assert result.new_rev == 2
    assert result.changed_paths == ("/sourcing",)
    assert host.transactions[0].holder == "ops-agent"
    assert host.transactions[0].ops[0]["op"] == "add"


def test_ir_transact_conflict(tmp_path: Path) -> None:
    host = FakePluginHost(root=tmp_path, rev=5)
    with pytest.raises(ValueError, match="revision conflict"):
        host.ir_transact("/sourcing", 4, [])


def test_events_and_cache_and_logger(tmp_path: Path) -> None:
    host = FakePluginHost(root=tmp_path)
    host.emit("ir.changed", {"rev": 1})
    assert host.events == [("ir.changed", {"rev": 1})]

    host.cache.set("k", 1, ttl_s=60)
    assert host.cache.get("k") == 1
    host.cache.delete("k")
    assert host.cache.get("k") is None

    host.logger.info("hello", plugin="sourcing")
    assert host.logger.records == [("info", "hello", {"plugin": "sourcing"})]


def test_artifact_root_created(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    host = FakePluginHost(root=root)
    assert host.artifact_root == root
    assert root.is_dir()
