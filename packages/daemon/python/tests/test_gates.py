"""Gate runner: persistence, advisory vs blocking, crash -> ERROR, events and listing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from atomcd.events import EventBus
from atomcd.gates import GateRunner
from atomcd.ir_store import IRStore
from atomcd.plugins.registry import PluginRegistry
from fakes import make_plugin

GATE = {
    "id": "gate:demo.stock",
    "severity": "blocking",
    "owner_agent": "ops-agent",
    "after": [],
    "handler": "check",
}


def setup(
    tmp_path: Path, obj: Any, gate: dict[str, Any] = GATE
) -> tuple[GateRunner, IRStore, EventBus]:
    store = IRStore(tmp_path)
    store.load()
    events = EventBus()
    registry = PluginRegistry(store=store, events=events, project_root=tmp_path)
    registry.add(make_plugin("demo", obj=obj, produces=["/sourcing"], gates=[gate]))
    return GateRunner(registry=registry, store=store, events=events), store, events


class PassPlugin:
    def check(self, ctx: Any) -> dict[str, Any]:
        return {"status": "PASS", "summary": "all good", "refs": []}


class AdvisoryFailPlugin:
    def check(self, ctx: Any) -> dict[str, Any]:
        return {"status": "FAIL", "summary": "2 lines out of stock"}


class CrashPlugin:
    def check(self, ctx: Any) -> dict[str, Any]:
        raise RuntimeError("boom secret-token-leak")


async def test_pass_gate_persists_and_emits(tmp_path: Path) -> None:
    runner, store, events = setup(tmp_path, PassPlugin())
    subscription = events.subscribe(["gate.result"])
    result = await runner.run_one("gate:demo.stock")
    assert result["status"] == "PASS"
    assert result["plugin"] == "plugin:demo@0.1.0"
    assert result["severity"] == "blocking"
    assert result["owner_agent"] == "ops-agent"
    assert result["ir_rev"] == 0  # evaluated before the result bumps the doc rev
    assert result["evaluated_at"]
    assert not subscription.queue.empty()

    _rev, gates = store.read("/gates")
    assert gates["results"]["demo.stock"]["status"] == "PASS"
    assert runner.list_results() == [result]
    assert runner.list_results(ids=["gate:demo.stock"]) == [result]
    assert runner.list_results(ids=["gate:other"]) == []


async def test_advisory_fail_does_not_raise(tmp_path: Path) -> None:
    advisory = dict(GATE, severity="advisory")
    runner, _store, _events = setup(tmp_path, AdvisoryFailPlugin(), gate=advisory)
    result = await runner.run_one("gate:demo.stock")
    assert result["status"] == "FAIL"
    assert result["severity"] == "advisory"


async def test_crash_becomes_error_with_sanitized_evidence(tmp_path: Path) -> None:
    runner, _store, _events = setup(tmp_path, CrashPlugin())
    result = await runner.run_one("gate:demo.stock")
    assert result["status"] == "ERROR"
    assert result["evidence"][0]["kind"] == "text"
    assert "RuntimeError: boom secret-token-leak" in result["summary"]


async def test_unknown_gate_returns_error(tmp_path: Path) -> None:
    runner, _store, _events = setup(tmp_path, PassPlugin())
    result = await runner.run_one("gate:missing")
    assert result["status"] == "ERROR"
    assert result["plugin"] == "plugin:unknown"


async def test_run_all_declared_gates(tmp_path: Path) -> None:
    runner, _store, _events = setup(tmp_path, PassPlugin())
    results = await runner.run()
    assert [r["id"] for r in results] == ["gate:demo.stock"]


async def test_missing_handler_is_error(tmp_path: Path) -> None:
    store = IRStore(tmp_path)
    store.load()
    events = EventBus()
    registry = PluginRegistry(store=store, events=events, project_root=tmp_path)
    registry.add(
        make_plugin(
            "demo",
            obj=PassPlugin(),
            produces=["/sourcing"],
            gates=[dict(GATE, handler="not_implemented")],
        )
    )
    runner = GateRunner(registry=registry, store=store, events=events)
    result = await runner.run_one("gate:demo.stock")
    assert result["status"] == "ERROR"
    assert "not implemented" in result["summary"]
