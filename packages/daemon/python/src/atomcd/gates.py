"""Gate runner: execute declared plugin gates and persist frozen ``GateResult`` objects.

Advisory FAIL/ERROR never blocks a DAG run; a crashed handler becomes ``ERROR`` with sanitized
evidence (message + type, no stack trace — the stack stays in the daemon log). Results are stored
at ``/gates/results/<id without 'gate:' prefix>`` and broadcast as ``gate.result`` events.
"""

from __future__ import annotations

import time
from typing import Any, Literal

from atomc_core_ir import GateResult
from pydantic import ValidationError

from .common import utcnow_iso
from .plugins.invoke import invoke
from .plugins.registry import PluginRegistry

ERROR_STATUS = "ERROR"


def _sanitize(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


class GateRunner:
    """Runs gates declared by loaded plugins."""

    def __init__(
        self,
        *,
        registry: PluginRegistry,
        store: Any,
        events: Any,
        logger: Any | None = None,
    ) -> None:
        self.registry = registry
        self.store = store
        self.events = events
        self.logger = logger

    # -- queries ------------------------------------------------------------

    def list_results(self, ids: list[str] | None = None) -> list[dict[str, Any]]:
        """Return stored gate results, optionally filtered by gate id."""
        try:
            _rev, value = self.store.read("/gates")
        except Exception:
            return []
        results: dict[str, Any] = value.get("results", {}) if isinstance(value, dict) else {}
        selected = list(results.values())
        if ids:
            wanted = set(ids)
            selected = [r for r in selected if r.get("id") in wanted]
        return sorted(selected, key=lambda r: str(r.get("id", "")))

    # -- execution ----------------------------------------------------------

    async def run(self, ids: list[str] | None = None) -> list[dict[str, Any]]:
        """Run the requested gates (all declared gates when ``ids`` is omitted)."""
        gate_ids = list(ids) if ids else [gate.id for _plugin, gate in self.registry.all_gates()]
        return [await self.run_one(gate_id) for gate_id in gate_ids]

    async def run_one(self, gate_id: str) -> dict[str, Any]:
        """Run a single gate and persist its result."""
        found = self.registry.find_gate(gate_id)
        started = time.perf_counter()
        if found is None:
            result = self._error_result(
                gate_id=gate_id,
                plugin="plugin:unknown",
                owner_agent=None,
                severity="blocking",
                message=f"gate {gate_id!r} is not declared by any loaded plugin",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        else:
            plugin, _gate = found
            result = await self._run_declared(plugin.name, gate_id, started)
        await self._persist(gate_id, result)
        self.events.publish("gate.result", result)
        return result

    async def _run_declared(self, plugin_name: str, gate_id: str, started: float) -> dict[str, Any]:
        plugin = self.registry.by_name(plugin_name)
        assert plugin is not None  # find_gate came from the registry
        gate = plugin.manifest.gate(gate_id)
        assert gate is not None  # find_gate came from the registry
        severity = gate.severity
        owner = gate.owner_agent
        handler = plugin.handler(gate.handler)
        if handler is None:
            return self._error_result(
                gate_id=gate_id,
                plugin=f"plugin:{plugin.name}@{plugin.manifest.version}",
                owner_agent=owner,
                severity=severity,
                message=f"handler {gate.handler!r} is not implemented",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        ctx = self.registry.make_context(plugin, holder=f"gate:{gate_id}")
        try:
            raw = await invoke(handler, ctx)
        except Exception as exc:
            if self.logger is not None:
                self.logger.exception("gate_crashed", gate=gate_id, plugin=plugin.name)
            return self._error_result(
                gate_id=gate_id,
                plugin=f"plugin:{plugin.name}@{plugin.manifest.version}",
                owner_agent=owner,
                severity=severity,
                message=_sanitize(exc),
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        return self._normalize(
            gate_id=gate_id,
            plugin=plugin.name,
            plugin_version=plugin.manifest.version,
            severity=severity,
            owner_agent=owner,
            raw=raw,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    def _normalize(
        self,
        *,
        gate_id: str,
        plugin: str,
        plugin_version: str,
        severity: Literal["blocking", "advisory"],
        owner_agent: str | None,
        raw: Any,
        duration_ms: int,
    ) -> dict[str, Any]:
        payload: dict[str, Any]
        if isinstance(raw, GateResult):
            payload = raw.model_dump(mode="json", by_alias=True)
        elif isinstance(raw, dict):
            payload = dict(raw)
        else:
            return self._error_result(
                gate_id=gate_id,
                plugin=f"plugin:{plugin}@{plugin_version}",
                owner_agent=owner_agent,
                severity=severity,
                message=f"gate returned unsupported value {type(raw).__name__}",
                duration_ms=duration_ms,
            )
        payload["id"] = gate_id
        payload["plugin"] = f"plugin:{plugin}@{plugin_version}"
        payload["severity"] = severity
        payload["owner_agent"] = owner_agent
        payload["evaluated_at"] = payload.get("evaluated_at") or utcnow_iso()
        payload["ir_rev"] = self.store.rev
        payload["duration_ms"] = payload.get("duration_ms", duration_ms)
        payload.setdefault("summary", "")
        payload.setdefault("evidence", [])
        payload.setdefault("suggestions", [])
        payload.setdefault("refs", [])
        payload.setdefault("status", ERROR_STATUS)
        return payload

    def _error_result(
        self,
        *,
        gate_id: str,
        plugin: str,
        owner_agent: str | None,
        severity: Literal["blocking", "advisory"],
        message: str,
        duration_ms: int,
    ) -> dict[str, Any]:
        return {
            "id": gate_id,
            "status": ERROR_STATUS,
            "severity": severity,
            "plugin": plugin,
            "owner_agent": owner_agent,
            "evaluated_at": utcnow_iso(),
            "ir_rev": self.store.rev,
            "duration_ms": duration_ms,
            "summary": message,
            "evidence": [{"kind": "text", "message": message}],
            "suggestions": [],
            "refs": [],
        }

    async def _persist(self, gate_id: str, result: dict[str, Any]) -> None:
        key = gate_id.removeprefix("gate:")
        try:
            await self.store.map_upsert("/gates", "results", key, result)
        except ValidationError, ValueError:
            if self.logger is not None:
                self.logger.exception("gate_persist_failed", gate=gate_id)


__all__ = ["ERROR_STATUS", "GateRunner"]
