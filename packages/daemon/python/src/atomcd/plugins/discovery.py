"""Plugin discovery from the project tree and the ``atomc.plugins`` entry-point group.

Discovery is deliberately fault-isolated: a malformed manifest or missing handler marks only that
plugin as ``loaded=False`` with an ``error``; the daemon keeps running and reports it through
``plugins.list``.
"""

from __future__ import annotations

import importlib
import importlib.metadata
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .manifest import MANIFEST_FILENAME, Manifest, ManifestError, Runtime, load_manifest
from .registry import LoadedPlugin, PluginRegistry

IGNORED_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache"}


def _placeholder_manifest(name: str) -> Manifest:
    runtime = Runtime.model_construct(python=None, ts=None)
    return Manifest.model_construct(
        manifest_version="0.1.0",
        name=name,
        version="0.0.0",
        description="",
        atomc="*",
        runtime=runtime,
        watches=[],
        produces=[],
        gates=[],
        tools=[],
        cli=[],
        ui=[],
    )


def _declared_handlers(manifest: Manifest) -> list[str]:
    names = [gate.handler for gate in manifest.gates]
    names += [tool.handler for tool in manifest.tools]
    names += [command.handler for command in manifest.cli]
    return [name for name in names if name]


def _load_python_runtime(plugin: LoadedPlugin, spec: str) -> None:
    module_name, _, attr = spec.partition(":")
    module = importlib.import_module(module_name)
    obj: Any = getattr(module, attr) if attr else module
    if isinstance(obj, type):
        obj = obj()
    plugin.plugin = obj
    node_handlers = getattr(obj, "__atomc_node_handlers__", None)
    if isinstance(node_handlers, dict):
        plugin.node_handlers.update(node_handlers)
    missing = [
        name for name in _declared_handlers(plugin.manifest) if getattr(obj, name, None) is None
    ]
    if missing:
        plugin.error = f"missing handler implementations: {sorted(set(missing))}"


def load_plugin(manifest: Manifest, *, source: str, root: Path | None) -> LoadedPlugin:
    """Build a :class:`LoadedPlugin` by importing its declared Python runtime (if any)."""
    plugin = LoadedPlugin(manifest=manifest, source=source, root=root)
    if manifest.runtime.python:
        try:
            _load_python_runtime(plugin, manifest.runtime.python)
        except Exception as exc:
            plugin.error = f"failed to import {manifest.runtime.python!r}: {exc}"
    else:
        plugin.error = "no python runtime declared; daemon cannot load TS-only plugin"
    return plugin


def _iter_project_manifests(project_root: Path) -> Iterable[Path]:
    if not project_root.exists():
        return []
    results: list[Path] = []
    for path in project_root.rglob(MANIFEST_FILENAME):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        results.append(path)
    return sorted(results)


def discover_from_project(project_root: Path) -> list[LoadedPlugin]:
    """Scan a project tree for ``atomc-plugin.json`` files."""
    plugins: list[LoadedPlugin] = []
    for manifest_path in _iter_project_manifests(project_root):
        name = manifest_path.parent.name or "unknown"
        try:
            manifest = load_manifest(manifest_path)
        except ManifestError as exc:
            plugin = LoadedPlugin(
                manifest=_placeholder_manifest(name),
                source=str(manifest_path),
                root=manifest_path.parent,
                error=str(exc),
            )
            plugins.append(plugin)
            continue
        plugins.append(load_plugin(manifest, source=str(manifest_path), root=manifest_path.parent))
    return plugins


def discover_from_entry_points(entry_points: Iterable[Any] | None = None) -> list[LoadedPlugin]:
    """Load plugins advertised via the ``atomc.plugins`` entry-point group."""
    if entry_points is None:
        entry_points = importlib.metadata.entry_points(group="atomc.plugins")
    plugins: list[LoadedPlugin] = []
    for entry in entry_points:
        name = getattr(entry, "name", "unknown")
        value = getattr(entry, "value", "") or ""
        try:
            manifest, root = _resolve_entry(entry, value)
        except ManifestError as exc:
            plugins.append(
                LoadedPlugin(
                    manifest=_placeholder_manifest(name),
                    source=value or name,
                    error=str(exc),
                )
            )
            continue
        plugin = load_plugin(manifest, source=value or name, root=root)
        if plugin.plugin is None and plugin.error is None:
            plugin.error = "entry point did not resolve a plugin object"
        plugins.append(plugin)
    return plugins


def _resolve_entry(entry: Any, value: str) -> tuple[Manifest, Path | None]:
    if value.endswith(".json"):
        path = Path(value)
        return load_manifest(path), path.parent
    loader = getattr(entry, "load", None)
    obj = loader() if callable(loader) else _import_spec(value)
    if isinstance(obj, type):
        obj = obj()
    manifest_obj = getattr(obj, "__atomc_manifest__", None) or getattr(obj, "manifest", None)
    if manifest_obj is None:
        raise ManifestError(f"entry point {value!r} exposes no __atomc_manifest__")
    if isinstance(manifest_obj, Manifest):
        return manifest_obj, None
    return Manifest.model_validate(manifest_obj), None


def _import_spec(spec: str) -> Any:
    module_name, _, attr = spec.partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, attr) if attr else module


def discover(
    project_root: Path,
    *,
    entry_points: Iterable[Any] | None = None,
    include_entry_points: bool = True,
) -> list[LoadedPlugin]:
    """Discover project plugins and (optionally) installed entry-point plugins."""
    plugins = discover_from_project(project_root)
    if include_entry_points:
        plugins.extend(discover_from_entry_points(entry_points))
    return plugins


def build_registry(
    project_root: Path,
    *,
    store: Any,
    events: Any,
    logger: Any | None = None,
    entry_points: Iterable[Any] | None = None,
    include_entry_points: bool = True,
    extra_plugins: Iterable[LoadedPlugin] | None = None,
) -> PluginRegistry:
    """Discover plugins and register them into a new :class:`PluginRegistry`."""
    registry = PluginRegistry(
        store=store,
        events=events,
        project_root=project_root,
        logger=logger,
    )
    for plugin in discover(
        project_root, entry_points=entry_points, include_entry_points=include_entry_points
    ):
        registry.add(plugin)
    for plugin in extra_plugins or []:
        registry.add(plugin)
    return registry


__all__ = [
    "build_registry",
    "discover",
    "discover_from_entry_points",
    "discover_from_project",
    "load_plugin",
]
