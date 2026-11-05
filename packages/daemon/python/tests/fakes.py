"""Shared fake plugins/manifests for daemon tests (no hardware engines)."""

from __future__ import annotations

from typing import Any

from atomcd.plugins.manifest import Manifest
from atomcd.plugins.registry import LoadedPlugin


def manifest_dict(
    name: str = "demo",
    *,
    watches: list[dict[str, Any]] | None = None,
    gates: list[dict[str, Any]] | None = None,
    tools: list[dict[str, Any]] | None = None,
    produces: list[str] | None = None,
    cli: list[dict[str, Any]] | None = None,
    ui: list[dict[str, Any]] | None = None,
    version: str = "0.1.0",
    python: str = "fake:plugin",
) -> dict[str, Any]:
    return {
        "manifest_version": "0.1.0",
        "name": name,
        "version": version,
        "description": f"{name} fake plugin",
        "atomc": ">=0.0.1 <0.2.0",
        "runtime": {"python": python},
        "watches": watches or [],
        "produces": produces or [],
        "gates": gates or [],
        "tools": tools or [],
        "cli": cli or [],
        "ui": ui or [],
    }


def make_manifest(name: str = "demo", **kwargs: Any) -> Manifest:
    return Manifest.model_validate(manifest_dict(name, **kwargs))


def make_plugin(
    name: str = "demo",
    *,
    obj: Any | None = None,
    node_handlers: dict[str, Any] | None = None,
    error: str | None = None,
    **kwargs: Any,
) -> LoadedPlugin:
    return LoadedPlugin(
        manifest=make_manifest(name, **kwargs),
        plugin=obj,
        source=f"fake:{name}",
        node_handlers=dict(node_handlers or {}),
        error=error,
    )


__all__ = ["make_manifest", "make_plugin", "manifest_dict"]
