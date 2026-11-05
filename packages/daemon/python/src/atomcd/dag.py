"""Reactive DAG scheduler over plugin watches and gates.

Nodes are watch ids (plugin "producers") and gate ids. Edges come from:

* explicit gate ``after`` references, and
* a plugin's declared ``produces`` scopes covering another watch's ``ir`` pointers.

Execution is incremental: a node is skipped when its content hash (watched IR subtrees + watched
file hashes + upstream outputs) is unchanged since the last successful run, unless ``force`` is
set. Each node has its own async lock; runs are topologically ordered. Cycles are rejected at
build time. Provenance is written to ``/provenance/nodes/<id>``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import networkx as nx  # type: ignore[import-untyped,unused-ignore]

from .common import utcnow_iso
from .plugins.context import pointer_allowed
from .plugins.invoke import invoke
from .plugins.registry import PluginRegistry

NodeState = Literal["idle", "queued", "running", "ok", "failed", "stale"]


class CycleError(ValueError):
    """The derived DAG contains a cycle."""


@dataclass
class DagNode:
    id: str
    plugin: str
    kind: Literal["watch", "gate"]
    ir: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    after: list[str] = field(default_factory=list)
    debounce_ms: int = 250


def _sha256(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return "sha256:" + hashlib.sha256(b"").hexdigest()
    return "sha256:" + hashlib.sha256(data).hexdigest()


class DagScheduler:
    """Builds and runs the reactive DAG for one daemon instance."""

    def __init__(
        self,
        *,
        registry: PluginRegistry,
        store: Any,
        events: Any,
        gate_runner: Any | None = None,
        logger: Any | None = None,
        debounce_ms: int = 0,
    ) -> None:
        self.registry = registry
        self.store = store
        self.events = events
        self.gate_runner = gate_runner
        self.logger = logger
        self.default_debounce_ms = debounce_ms
        self.project_root: Path = registry.project_root
        self._graph = nx.DiGraph()
        self._nodes: dict[str, DagNode] = {}
        self._state: dict[str, NodeState] = {}
        self._last_run: dict[str, str] = {}
        self._last_inputs: dict[str, str] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._run_counter = 0
        self._pending_paths: set[str] = set()
        self._pending_files: set[str] = set()
        self._debounce_task: asyncio.Task[None] | None = None
        self.build()

    # -- graph construction -------------------------------------------------

    def build(self) -> None:
        """Derive nodes and edges from the registry; raise :class:`CycleError` on cycles."""
        self._graph = nx.DiGraph()
        self._nodes = {}
        self._state = {}
        self._locks = {}
        for plugin, watch in self.registry.all_watches():
            self._add_node(
                DagNode(
                    id=watch.id,
                    plugin=plugin.name,
                    kind="watch",
                    ir=list(watch.ir),
                    files=list(watch.files),
                    debounce_ms=watch.debounce_ms,
                )
            )
        for plugin, gate in self.registry.all_gates():
            self._add_node(
                DagNode(
                    id=gate.id,
                    plugin=plugin.name,
                    kind="gate",
                    after=list(gate.after),
                    debounce_ms=self.default_debounce_ms,
                )
            )

        # Explicit after edges.
        for node in self._nodes.values():
            for dependency in node.after:
                if dependency in self._nodes:
                    self._graph.add_edge(dependency, node.id)

        # Producer -> consumer edges from produces scopes covering watched pointers.
        watches = [n for n in self._nodes.values() if n.kind == "watch"]
        for producer in watches:
            owner = self.registry.by_name(producer.plugin)
            produces = owner.manifest.produces if owner else []
            if not produces:
                continue
            for consumer in watches:
                if consumer.id == producer.id:
                    continue
                if any(pointer_allowed(produces, pointer) for pointer in consumer.ir):
                    self._graph.add_edge(producer.id, consumer.id)

        if not nx.is_directed_acyclic_graph(self._graph):
            cycle = nx.find_cycle(self._graph)
            raise CycleError(f"plugin DAG contains a cycle: {cycle}")

    def _add_node(self, node: DagNode) -> None:
        self._nodes[node.id] = node
        self._graph.add_node(node.id)
        self._state[node.id] = "idle"
        self._locks[node.id] = asyncio.Lock()

    # -- introspection ------------------------------------------------------

    @property
    def nodes(self) -> dict[str, DagNode]:
        return dict(self._nodes)

    def status(self) -> dict[str, Any]:
        return {
            "nodes": [
                {
                    "id": node.id,
                    "plugin": node.plugin,
                    "kind": node.kind,
                    "state": self._state[node.id],
                    **({"last_run": self._last_run[node.id]} if node.id in self._last_run else {}),
                }
                for node in self._nodes.values()
            ]
        }

    def states(self) -> dict[str, NodeState]:
        return dict(self._state)

    def edges(self) -> list[tuple[str, str]]:
        """Return the derived DAG edges as ``(dependency, dependent)`` pairs."""
        return list(self._graph.edges())

    # -- change routing -----------------------------------------------------

    def nodes_for_paths(self, changed_paths: list[str]) -> list[str]:
        """Watch nodes whose ``ir`` pointers cover any changed path, plus descendants."""
        direct = [
            node.id
            for node in self._nodes.values()
            if node.kind == "watch"
            and any(
                pointer_allowed([pointer], changed) or pointer_allowed([changed], pointer)
                for pointer in node.ir
                for changed in changed_paths
            )
        ]
        return self._with_descendants(direct)

    def nodes_for_files(self, changed_files: list[str]) -> list[str]:
        """Watch nodes whose file globs match changed project files, plus descendants."""
        import fnmatch

        direct = []
        for node in self._nodes.values():
            if node.kind != "watch":
                continue
            for pattern in node.files:
                if any(fnmatch.fnmatch(path, pattern) for path in changed_files):
                    direct.append(node.id)
                    break
        return self._with_descendants(direct)

    def _with_descendants(self, node_ids: list[str]) -> list[str]:
        result: set[str] = set()
        for node_id in node_ids:
            if node_id not in self._graph:
                continue
            result.add(node_id)
            result.update(nx.descendants(self._graph, node_id))
        return sorted(result, key=self._topo_index)

    def _topo_index(self, node_id: str) -> int:
        try:
            return list(nx.topological_sort(self._graph)).index(node_id)
        except nx.NetworkXError, ValueError:  # pragma: no cover - defensive
            return 0

    def notify_ir_changed(self, changed_paths: list[str]) -> None:
        """Schedule affected nodes after an IR change (debounced)."""
        self._pending_paths.update(changed_paths)
        self._schedule_debounce()

    def notify_files_changed(self, changed_files: list[str]) -> None:
        self._pending_files.update(changed_files)
        self._schedule_debounce()

    def _schedule_debounce(self) -> None:
        if self._debounce_task is not None and not self._debounce_task.done():
            return
        self._debounce_task = self._track(asyncio.create_task(self._debounced_run()))

    async def _debounced_run(self) -> None:
        delay = self.default_debounce_ms / 1000
        if delay:
            await asyncio.sleep(delay)
        paths = sorted(self._pending_paths)
        files = sorted(self._pending_files)
        self._pending_paths.clear()
        self._pending_files.clear()
        targets = sorted(
            set(self.nodes_for_paths(paths)) | set(self.nodes_for_files(files)),
            key=self._topo_index,
        )
        if targets:
            await self.run(targets=targets)

    # -- execution ----------------------------------------------------------

    def _track(self, task: asyncio.Task[None]) -> asyncio.Task[None]:
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def wait_idle(self) -> None:
        """Await all in-flight runs (test/CLI helper)."""
        if self._debounce_task is not None:
            await asyncio.gather(self._debounce_task, return_exceptions=True)
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def run(self, targets: list[str] | None = None, force: bool = False) -> str:
        """Schedule a run and return its ``run_id`` immediately."""
        self._run_counter += 1
        run_id = f"run-{self._run_counter}"
        self._track(asyncio.create_task(self._execute(run_id, targets, force)))
        return run_id

    def _ordered_targets(self, targets: list[str] | None) -> list[str]:
        if not targets:
            return list(nx.topological_sort(self._graph))
        wanted: set[str] = set()
        for target in targets:
            if target not in self._graph:
                raise KeyError(f"unknown DAG node {target!r}")
            wanted.add(target)
            wanted.update(nx.ancestors(self._graph, target))
        order = [n for n in nx.topological_sort(self._graph) if n in wanted]
        return order

    async def _execute(self, run_id: str, targets: list[str] | None, force: bool) -> None:
        order = self._ordered_targets(targets)
        for node_id in order:
            node = self._nodes[node_id]
            input_hash = self.input_hash(node_id)
            if (
                not force
                and self._state[node_id] == "ok"
                and self._last_inputs.get(node_id) == input_hash
            ):
                continue
            self._state[node_id] = "queued"
            self.events.publish(
                "dag.node.start", {"run_id": run_id, "id": node_id, "plugin": node.plugin}
            )
            started = time.perf_counter()
            try:
                async with self._locks[node_id]:
                    self._state[node_id] = "running"
                    outputs_hash = await self._run_node(node)
            except Exception as exc:
                self._state[node_id] = "failed"
                duration_ms = int((time.perf_counter() - started) * 1000)
                self.events.publish(
                    "dag.node.end",
                    {
                        "run_id": run_id,
                        "id": node_id,
                        "ok": False,
                        "duration_ms": duration_ms,
                        "error": str(exc),
                    },
                )
                raise
            duration_ms = int((time.perf_counter() - started) * 1000)
            self._state[node_id] = "ok"
            self._last_inputs[node_id] = input_hash
            self._last_run[node_id] = utcnow_iso()
            await self._write_provenance(node, input_hash, outputs_hash, duration_ms)
            self.events.publish(
                "dag.node.end",
                {"run_id": run_id, "id": node_id, "ok": True, "duration_ms": duration_ms},
            )

    async def _run_node(self, node: DagNode) -> str:
        if node.kind == "gate":
            if self.gate_runner is None:
                return _sha256({"skipped": node.id})
            result = await self.gate_runner.run_one(node.id)
            return _sha256(result)
        plugin = self.registry.by_name(node.plugin)
        if plugin is None:
            return _sha256({"no_plugin": node.plugin})
        handler = plugin.node_handlers.get(node.id)
        if handler is None:
            # A watch with no registered handler is a pure invalidation node.
            return _sha256({"no_handler": node.id})
        ctx = self.registry.make_context(plugin)
        outcome = await invoke(handler, ctx)
        return _sha256(outcome)

    async def _write_provenance(
        self, node: DagNode, inputs_hash: str, outputs_hash: str, duration_ms: int
    ) -> None:
        record = {
            "producer": f"plugin:{node.plugin}",
            "inputs_hash": inputs_hash,
            "outputs_hash": outputs_hash,
            "ran_at": utcnow_iso(),
            "duration_ms": duration_ms,
        }
        try:
            await self.store.map_upsert("/provenance", "nodes", node.id, record)
        except Exception:
            if self.logger is not None:
                self.logger.warning("provenance_write_failed", node=node.id)

    # -- hashing ------------------------------------------------------------

    def input_hash(self, node_id: str) -> str:
        node = self._nodes[node_id]
        payload: dict[str, Any] = {"ir": [], "files": [], "upstream": []}
        for pointer in node.ir:
            try:
                _rev, value = self.store.read(pointer)
            except Exception:
                value = None
            payload["ir"].append({"pointer": pointer, "value": value})
        for pattern in node.files:
            matches = sorted(self.project_root.glob(pattern))
            payload["files"].append(
                {str(path): _file_hash(path) for path in matches if path.is_file()}
            )
        for predecessor in self._graph.predecessors(node_id):
            payload["upstream"].append(
                {"id": predecessor, "inputs": self._last_inputs.get(predecessor)}
            )
        return _sha256(payload)


__all__ = ["CycleError", "DagNode", "DagScheduler", "NodeState"]
