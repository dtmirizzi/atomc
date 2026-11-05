"""End-to-end JSON-RPC wiring: plugins.list, tools.list/call, gates.run, dag.status/run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from atomcd.app import Services, create_app
from atomcd.config import DaemonConfig
from atomcd.dag import DagScheduler
from atomcd.events import EventBus
from atomcd.gates import GateRunner
from atomcd.ir_store import IRStore
from atomcd.plugins.registry import PluginRegistry
from atomcd.runtime import RuntimeState
from fakes import make_plugin
from fastapi.testclient import TestClient


class FakeDomainPlugin:
    def __init__(self) -> None:
        self.node_calls = 0

    def check_stock(self, ctx: Any) -> dict[str, Any]:
        return {"status": "PASS", "summary": "in stock"}

    async def search(self, ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
        return {"result": {"hits": [args.get("q", "")]}}

    def refresh(self, ctx: Any) -> str:
        self.node_calls += 1
        return "refreshed"


def build_services(tmp_path: Path) -> Services:
    config = DaemonConfig(
        project_root=tmp_path, state_dir=tmp_path / "state", token="integration-token"
    )
    store = IRStore(tmp_path)
    store.load()
    events = EventBus()
    registry = PluginRegistry(store=store, events=events, project_root=tmp_path)
    obj = FakeDomainPlugin()
    registry.add(
        make_plugin(
            "sourcing",
            obj=obj,
            produces=["/sourcing"],
            watches=[{"id": "sourcing:refresh", "ir": ["/electrical"], "debounce_ms": 0}],
            gates=[
                {
                    "id": "gate:sourcing.stock",
                    "severity": "advisory",
                    "owner_agent": "ops-agent",
                    "after": ["sourcing:refresh"],
                    "handler": "check_stock",
                }
            ],
            tools=[
                {
                    "name": "search",
                    "description": "find parts",
                    "input_schema": {},
                    "agents": ["ee-agent"],
                    "mutates": False,
                    "handler": "search",
                }
            ],
            node_handlers={"sourcing:refresh": obj.refresh},
        )
    )
    gates = GateRunner(registry=registry, store=store, events=events)
    dag = DagScheduler(registry=registry, store=store, events=events, gate_runner=gates)
    runtime = RuntimeState(config.state_dir)
    runtime.write(
        pid=1,
        host="127.0.0.1",
        port=7437,
        token="integration-token",
        project_root=str(tmp_path),
        version="0.0.1",
    )
    return Services(
        config=config,
        store=store,
        runtime_state=runtime,
        events=events,
        version="0.0.1",
        dag=dag,
        gates=gates,
        plugins=registry,
    )


def rpc(client: TestClient, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    with client.websocket_connect(
        "/rpc", headers={"Authorization": "Bearer integration-token"}
    ) as ws:
        ws.send_text(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})
        )
        while True:
            message = ws.receive_json()
            if message.get("method") == "event":
                continue
            return cast("dict[str, Any]", message)


def test_plugins_list_and_tools(tmp_path: Path) -> None:
    client = TestClient(create_app(build_services(tmp_path)))
    plugins = rpc(client, "plugins.list")["result"]
    assert plugins[0]["name"] == "sourcing"
    assert plugins[0]["loaded"] is True
    tools = rpc(client, "tools.list", {"agent": "ee-agent"})["result"]
    assert [t["name"] for t in tools] == ["search"]
    assert rpc(client, "tools.list", {"agent": "mech-agent"})["result"] == []


def test_tools_call(tmp_path: Path) -> None:
    client = TestClient(create_app(build_services(tmp_path)))
    result = rpc(client, "tools.call", {"plugin": "sourcing", "tool": "search", "args": {"q": "R"}})
    assert result["result"]["result"]["hits"] == ["R"]


def test_gates_run_and_list(tmp_path: Path) -> None:
    client = TestClient(create_app(build_services(tmp_path)))
    run = rpc(client, "gates.run", {"ids": ["gate:sourcing.stock"]})["result"]
    assert run[0]["status"] == "PASS"
    listed = rpc(client, "gates.list")["result"]
    assert [g["id"] for g in listed] == ["gate:sourcing.stock"]


def test_dag_status_and_run(tmp_path: Path) -> None:
    client = TestClient(create_app(build_services(tmp_path)))
    status = rpc(client, "dag.status")["result"]
    ids = {node["id"] for node in status["nodes"]}
    assert {"sourcing:refresh", "gate:sourcing.stock"} <= ids
    run = rpc(client, "dag.run", {"targets": ["sourcing:refresh"]})["result"]
    assert run["run_id"] == "run-1"
