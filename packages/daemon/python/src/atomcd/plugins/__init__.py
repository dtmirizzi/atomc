"""Plugin host: manifest parsing, discovery, registry and invocation context."""

from __future__ import annotations

from .context import PluginContext, ScopeError, pointer_allowed
from .discovery import build_registry, discover, discover_from_entry_points, discover_from_project
from .invoke import invoke
from .manifest import (
    MANIFEST_FILENAME,
    MANIFEST_VERSION,
    CliCommand,
    Gate,
    Manifest,
    ManifestError,
    Runtime,
    Tool,
    UiPanel,
    Watch,
    load_manifest,
    validate_manifest,
)
from .registry import LoadedPlugin, PluginRegistry

__all__ = [
    "MANIFEST_FILENAME",
    "MANIFEST_VERSION",
    "CliCommand",
    "Gate",
    "LoadedPlugin",
    "Manifest",
    "ManifestError",
    "PluginContext",
    "PluginRegistry",
    "Runtime",
    "ScopeError",
    "Tool",
    "UiPanel",
    "Watch",
    "build_registry",
    "discover",
    "discover_from_entry_points",
    "discover_from_project",
    "invoke",
    "load_manifest",
    "pointer_allowed",
    "validate_manifest",
]
