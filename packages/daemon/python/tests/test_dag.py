"""DAG derivation, cycle rejection, incremental scheduling, provenance and events."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from atomcd.dag import CycleError, DagScheduler
from atomcd.events import EventBus
from atomcd.ir_store import IRStore
from atomcd.plugins.registry import PluginRegistry
from atomcd.testing import make_plugin

ELECTRICAL_NODE: dict[str, Any] = {
    "_meta": {"rev": 0, "lock": None},
    "source": {"kind": "atopile", "entry": "main.ato:App"},
    "components": [],
    "nets": [],
    "assertions": [],
    "erc": [],
}


def make_registry(tmp_path: Path, events: EventBus) -> tuple[PluginRegistry, IRStore]:
    store = IRStore(tmp_path)
    store.load()
    return PluginRegistry(store=store, events=events, project_root=tmp_path), store


def test_edges_from_produces_and_after(tmp_path: Path) -> None:
    registry, _store = make_registry(tmp_path, EventBus())
    registry.add(
        make_plugin(
            "atopile",
            produces=["/electrical"],
            watches=[{"id": "atopile:build", "ir": ["/keyboard"], "debounce_ms": 0}],
        )
    )
    registry.add(
        make_plugin(
            "sourcing",
            watches=[{"id": "sourcing:refresh", "ir": ["/electrical/components"]}],
            gates=[
                {
                    "id": "gate:sourcing.stock",
                    "severity": "blocking",
                    "owner_agent": "ops-agent",
                    "after": ["atopile:build"],
                    "handler": "check",
                }
            ],
        )
    )
    dag = DagScheduler(registry=registry, store=registry.store, events=EventBus())
    edges = set(dag.edges())
    assert ("atopile:build", "sourcing:refresh") in edges
    assert ("atopile:build", "gate:sourcing.stock") in edges


def test_cycle_rejected(tmp_path: Path) -> None:
    registry, _store = make_registry(tmp_path, EventBus())
    registry.add(
        make_plugin(
            "a",
            produces=["/electrical"],
            watches=[{"id": "a:nu", "ir": ["/sourcing"]}],
        )
    )
    registry.add(
        make_plugin(
            "b",
            produces=["/sourcing"],
            watches=[{"id": "b:nu", "ir": ["/electrical"]}],
        )
    )
    with pytest.raises(CycleError):
        DagScheduler(registry=registry, store=registry.store, events=EventBus())


def test_nodes_for_paths_includes_descendants(tmp_path: Path) -> None:
    registry, _store = make_registry(tmp_path, EventBus())
    registry.add(
        make_plugin(
            "atopile",
            produces=["/electrical"],
            watches=[{"id": "atopile:build", "ir": ["/keyboard"]}],
        )
    )
    registry.add(
        make_plugin(
            "sourcing",
            watches=[{"id": "sourcing:refresh", "ir": ["/electrical/components"]}],
        )
    )
    dag = DagScheduler(registry=registry, store=registry.store, events=EventBus())
    assert dag.nodes_for_paths(["/electrical/components"]) == [
        "sourcing:refresh",
    ]
    # A change to /electrical also invalidates the downstream sourcing watch.
    assert set(dag.nodes_for_paths(["/electrical"])) == {"sourcing:refresh"}


async def test_incremental_run_skips_unchanged(tmp_path: Path) -> None:
    events = EventBus()
    registry, store = make_registry(tmp_path, events)
    calls: list[str] = []

    def handler(ctx: Any) -> str:
        calls.append("ran")
        return "ok"

    registry.add(
        make_plugin(
            "demo",
            produces=["/electrical"],
            watches=[{"id": "demo:watch", "ir": ["/electrical/components"], "debounce_ms": 0}],
            node_handlers={"demo:watch": handler},
        )
    )
    dag = DagScheduler(registry=registry, store=store, events=events)
    await dag.run(targets=["demo:watch"])
    await dag.wait_idle()
    assert calls == ["ran"]
    assert dag.states()["demo:watch"] == "ok"

    # Unchanged inputs -> skipped.
    await dag.run(targets=["demo:watch"])
    await dag.wait_idle()
    assert calls == ["ran"]

    # Force -> runs again.
    await dag.run(targets=["demo:watch"], force=True)
    await dag.wait_idle()
    assert calls == ["ran", "ran"]

    # Change a watched pointer -> runs again without force.
    await store.transact("/electrical", 0, [{"op": "add", "path": "", "value": ELECTRICAL_NODE}])
    await dag.run(targets=["demo:watch"])
    await dag.wait_idle()
    assert calls == ["ran", "ran", "ran"]


async def test_run_emits_events_and_provenance(tmp_path: Path) -> None:
    events = EventBus()
    subscription = events.subscribe(["dag.node.start", "dag.node.end"])
    registry, store = make_registry(tmp_path, events)
    registry.add(
        make_plugin(
            "demo",
            produces=["/electrical"],
            watches=[{"id": "demo:watch", "ir": ["/electrical/components"], "debounce_ms": 0}],
            node_handlers={"demo:watch": lambda ctx: "ok"},
        )
    )
    dag = DagScheduler(registry=registry, store=store, events=events)
    run_id = await dag.run(targets=["demo:watch"])
    await dag.wait_idle()
    assert run_id == "run-1"

    received = []
    while not subscription.queue.empty():
        received.append(subscription.queue.get_nowait())
    topics = [event.topic for event in received]
    assert "dag.node.start" in topics
    assert "dag.node.end" in topics

    _rev, provenance = store.read("/provenance")
    node = provenance["nodes"]["demo:watch"]
    assert node["producer"] == "plugin:demo"
    assert node["inputs_hash"].startswith("sha256:")
    assert node["outputs_hash"].startswith("sha256:")


async def test_debounced_notify_runs_affected_nodes(tmp_path: Path) -> None:
    events = EventBus()
    registry, store = make_registry(tmp_path, events)
    calls: list[str] = []

    def handler(ctx: Any) -> str:
        calls.append("x")
        return "ok"

    registry.add(
        make_plugin(
            "demo",
            watches=[{"id": "demo:watch", "ir": ["/electrical/components"], "debounce_ms": 0}],
            node_handlers={"demo:watch": handler},
        )
    )
    dag = DagScheduler(registry=registry, store=store, events=events, debounce_ms=0)
    dag.notify_ir_changed(["/electrical/components"])
    await dag.wait_idle()
    assert calls == ["x"]


def test_unknown_target_rejected(tmp_path: Path) -> None:
    registry, store = make_registry(tmp_path, EventBus())
    dag = DagScheduler(registry=registry, store=store, events=EventBus())
    with pytest.raises(KeyError):
        dag._ordered_targets(["nope"])


def test_status_shape(tmp_path: Path) -> None:
    registry, store = make_registry(tmp_path, EventBus())
    registry.add(make_plugin("demo", watches=[{"id": "demo:watch", "ir": ["/electrical"]}]))
    dag = DagScheduler(registry=registry, store=store, events=EventBus())
    status = dag.status()
    assert status["nodes"][0]["id"] == "demo:watch"
    assert status["nodes"][0]["state"] == "idle"
    assert json.loads(json.dumps(status))  # JSON serialisable
