"""Reusable fake plugins/manifests for daemon and integration tests.

Kept in the importable package (not ``tests/``) so cross-package tests (e.g. WP-2.6 RPC
contract tests) can construct deterministic plugins without duplicating helpers::

    from atomcd.testing import make_plugin

No hardware engines are imported.
"""

from __future__ import annotations

from typing import Any

from .plugins.manifest import Manifest
from .plugins.registry import LoadedPlugin


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
    """Build raw ``atomc-plugin.json`` data for a fake plugin."""
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
    """Validate and return a fake :class:`Manifest`."""
    return Manifest.model_validate(manifest_dict(name, **kwargs))


def make_plugin(
    name: str = "demo",
    *,
    obj: Any | None = None,
    node_handlers: dict[str, Any] | None = None,
    error: str | None = None,
    **kwargs: Any,
) -> LoadedPlugin:
    """Build a :class:`LoadedPlugin` around a fake manifest/object."""
    return LoadedPlugin(
        manifest=make_manifest(name, **kwargs),
        plugin=obj,
        source=f"fake:{name}",
        node_handlers=dict(node_handlers or {}),
        error=error,
    )


__all__ = ["make_manifest", "make_plugin", "manifest_dict"]
