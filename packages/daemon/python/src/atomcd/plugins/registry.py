"""Loaded-plugin registry: status listing, scope-enforcing tool calls, gate/watch lookup."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..errors import PluginFailureError
from ..events import EventBus
from ..ir_store import IRStore
from .context import PluginContext
from .invoke import invoke
from .manifest import Gate, Manifest, Tool, Watch


@dataclass
class LoadedPlugin:
    """A manifest plus its (optionally loaded) runtime implementation."""

    manifest: Manifest
    plugin: Any = None
    source: str = ""
    root: Path | None = None
    error: str | None = None
    node_handlers: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def loaded(self) -> bool:
        return self.error is None

    def handler(self, name: str) -> Any | None:
        if self.plugin is None:
            return None
        return getattr(self.plugin, name, None)


class ConflictError(ValueError):
    """Two loaded plugins declare the same globally-unique id."""


class PluginRegistry:
    """Holds loaded plugins and resolves handlers for the rest of the daemon."""

    def __init__(
        self,
        *,
        store: IRStore,
        events: EventBus,
        project_root: Path,
        artifact_root: Path | None = None,
        logger: Any | None = None,
    ) -> None:
        self.store = store
        self.events = events
        self.project_root = project_root
        self.artifact_root = artifact_root or (project_root / ".atomc" / "artifacts")
        self.logger = logger
        self._plugins: list[LoadedPlugin] = []
        self._cache: dict[str, dict[str, Any]] = {}

    # -- registration -------------------------------------------------------

    def add(self, plugin: LoadedPlugin) -> LoadedPlugin:
        """Register a plugin, isolating global-id conflicts as a plugin-level error."""
        conflict = self._conflict(plugin)
        if conflict is not None and plugin.error is None:
            plugin.error = conflict
        self._plugins.append(plugin)
        return plugin

    def _conflict(self, plugin: LoadedPlugin) -> str | None:
        for existing in self._plugins:
            if existing.error is not None:
                continue
            if set(w.id for w in plugin.manifest.watches) & set(
                w.id for w in existing.manifest.watches
            ):
                return f"watch id conflicts with plugin {existing.name!r}"
            if set(g.id for g in plugin.manifest.gates) & set(
                g.id for g in existing.manifest.gates
            ):
                return f"gate id conflicts with plugin {existing.name!r}"
            if set(c.command for c in plugin.manifest.cli) & set(
                c.command for c in existing.manifest.cli
            ):
                return f"cli command conflicts with plugin {existing.name!r}"
            if set(u.panel for u in plugin.manifest.ui) & set(
                u.panel for u in existing.manifest.ui
            ):
                return f"ui panel conflicts with plugin {existing.name!r}"
        return None

    @property
    def plugins(self) -> list[LoadedPlugin]:
        return list(self._plugins)

    def by_name(self, name: str) -> LoadedPlugin | None:
        for plugin in self._plugins:
            if plugin.name == name:
                return plugin
        return None

    # -- introspection ------------------------------------------------------

    def status_list(self) -> list[dict[str, Any]]:
        """``plugins.list`` payload: manifest + ``loaded`` + optional ``error``."""
        result: list[dict[str, Any]] = []
        for plugin in self._plugins:
            entry = plugin.manifest.model_dump(mode="json")
            entry["loaded"] = plugin.loaded
            entry["source"] = plugin.source
            if plugin.error is not None:
                entry["error"] = plugin.error
            result.append(entry)
        return result

    def tools_list(self, agent: str | None = None) -> list[dict[str, Any]]:
        """``tools.list`` payload, filtered by agent allow-list when supplied."""
        result: list[dict[str, Any]] = []
        for plugin in self._plugins:
            if plugin.error is not None:
                continue
            for tool in plugin.manifest.tools:
                if agent is not None and agent not in tool.agents:
                    continue
                result.append(
                    {
                        "plugin": plugin.name,
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.input_schema,
                        "mutates": tool.mutates,
                    }
                )
        return result

    def all_gates(self) -> list[tuple[LoadedPlugin, Gate]]:
        out: list[tuple[LoadedPlugin, Gate]] = []
        for plugin in self._plugins:
            if plugin.error is not None:
                continue
            for gate in plugin.manifest.gates:
                out.append((plugin, gate))
        return out

    def find_gate(self, gate_id: str) -> tuple[LoadedPlugin, Gate] | None:
        for plugin, gate in self.all_gates():
            if gate.id == gate_id:
                return plugin, gate
        return None

    def all_watches(self) -> list[tuple[LoadedPlugin, Watch]]:
        out: list[tuple[LoadedPlugin, Watch]] = []
        for plugin in self._plugins:
            if plugin.error is not None:
                continue
            for watch in plugin.manifest.watches:
                out.append((plugin, watch))
        return out

    def find_tool(self, plugin_name: str, tool_name: str) -> Tool | None:
        plugin = self.by_name(plugin_name)
        if plugin is None:
            return None
        return plugin.manifest.tool(tool_name)

    # -- execution ----------------------------------------------------------

    def make_context(self, plugin: LoadedPlugin, holder: str | None = None) -> PluginContext:
        cache = self._cache.setdefault(plugin.name, {})
        return PluginContext(
            plugin_name=plugin.name,
            holder=holder or f"plugin:{plugin.name}",
            store=self.store,
            produces=plugin.manifest.produces,
            artifact_root=self.artifact_root / plugin.name,
            cache=cache,
            logger=self.logger,
            events=self.events,
        )

    async def call_tool(
        self,
        plugin_name: str,
        tool_name: str,
        args: dict[str, Any],
        holder: str | None = None,
    ) -> dict[str, Any]:
        """Invoke a plugin tool, mapping failures to ``-32020``."""
        plugin = self.by_name(plugin_name)
        if plugin is None or plugin.error is not None:
            raise PluginFailureError(plugin_name, tool_name, False, "plugin not loaded")
        tool = plugin.manifest.tool(tool_name)
        if tool is None:
            raise PluginFailureError(plugin_name, tool_name, False, "unknown tool")
        handler = plugin.handler(tool.handler)
        if handler is None:
            raise PluginFailureError(
                plugin_name, tool_name, False, f"handler {tool.handler!r} not implemented"
            )
        ctx = self.make_context(plugin, holder=holder)
        try:
            outcome = await invoke(handler, ctx, args)
        except Exception as exc:
            if self.logger is not None:
                self.logger.exception("tool_failed", plugin=plugin_name, tool=tool_name)
            raise PluginFailureError(plugin_name, tool_name, False, str(exc)) from exc
        if isinstance(outcome, dict) and ("result" in outcome or "artifacts" in outcome):
            return {
                "result": outcome.get("result"),
                **({"artifacts": outcome["artifacts"]} if "artifacts" in outcome else {}),
            }
        return {"result": outcome}


__all__ = ["ConflictError", "LoadedPlugin", "PluginRegistry"]
