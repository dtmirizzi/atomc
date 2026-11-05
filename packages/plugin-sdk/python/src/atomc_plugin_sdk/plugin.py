"""Plugin decoration helpers and the ``AtomcPlugin`` protocol.

``@atomc_plugin(manifest=...)`` attaches a validated manifest to a class, factory function or
instance as ``__atomc_manifest__``. Decoration performs no plugin side effects beyond that
attribute assignment: no handler is imported, instantiated or invoked and no network/disk access
happens at import time.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol, TypeVar, runtime_checkable

from .host import PluginHost
from .manifest import PluginManifest, validate_manifest

__all__ = [
    "HANDLERS_ATTR",
    "MANIFEST_ATTR",
    "AtomcPlugin",
    "PluginDefinition",
    "PluginHost",
    "atomc_plugin",
    "define_plugin",
    "get_handlers",
    "get_manifest",
]

MANIFEST_ATTR = "__atomc_manifest__"
"""Attribute the validated :class:`PluginManifest` is attached to."""

HANDLERS_ATTR = "__atomc_handlers__"
"""Optional attribute holding a mapping of declared handler name -> callable."""

T = TypeVar("T")

ManifestLike = PluginManifest | Mapping[str, Any]
HandlerMap = Mapping[str, Callable[..., Any]]


@runtime_checkable
class AtomcPlugin(Protocol):
    """Structural protocol satisfied by a decorated plugin class or instance."""

    __atomc_manifest__: PluginManifest


@dataclass(frozen=True, slots=True)
class PluginDefinition:
    """An immutable pairing of a validated manifest with its registered handlers.

    The daemon (or a test) can run conformance on a definition directly, without importing a
    plugin module.
    """

    manifest: PluginManifest
    handlers: Mapping[str, Callable[..., Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "handlers", MappingProxyType(dict(self.handlers)))

    def resolve(self, name: str) -> Callable[..., Any] | None:
        """Return the callable registered for ``name``, if any."""
        return self.handlers.get(name)

    def __call__(self, target: T) -> T:
        """Allow a definition to also be used as a decorator."""
        return _attach(target, self.manifest, self.handlers or None)


def define_plugin(
    manifest: ManifestLike,
    *,
    handlers: HandlerMap | None = None,
) -> PluginDefinition:
    """Validate ``manifest`` and build an immutable :class:`PluginDefinition`."""
    parsed = _parse_manifest(manifest)
    return PluginDefinition(manifest=parsed, handlers=dict(handlers or {}))


def atomc_plugin(
    manifest: ManifestLike,
    *,
    handlers: HandlerMap | None = None,
) -> Callable[[T], T]:
    """Decorator attaching a validated manifest to a class, factory or instance.

    Usage::

        @atomc_plugin(manifest=manifest_dict)
        class MyPlugin:
            def my_gate(self, ctx): ...

    The manifest is validated eagerly (at decoration time) and stored as
    ``__atomc_manifest__``. When ``handlers`` is supplied it is stored as
    ``__atomc_handlers__`` and conformance rejects any handler not declared in the manifest.
    """
    parsed = _parse_manifest(manifest)
    registered = MappingProxyType(dict(handlers)) if handlers is not None else None

    def decorate(target: T) -> T:
        return _attach(target, parsed, registered)

    return decorate


def _attach[T](
    target: T,
    manifest: PluginManifest,
    handlers: HandlerMap | None,
) -> T:
    try:
        setattr(target, MANIFEST_ATTR, manifest)
        if handlers is not None:
            setattr(target, HANDLERS_ATTR, handlers)
    except (AttributeError, TypeError) as exc:  # e.g. slotted instances
        raise TypeError(
            f"cannot decorate {type(target).__name__}: it does not allow attribute assignment "
            "(use a class/factory or provide a PluginDefinition instead)"
        ) from exc
    return target


def _parse_manifest(manifest: ManifestLike) -> PluginManifest:
    if isinstance(manifest, PluginManifest):
        return manifest
    return validate_manifest(manifest)


def get_manifest(plugin: Any) -> PluginManifest | None:
    """Return the attached manifest from a class, factory or instance, if any."""
    return getattr(plugin, MANIFEST_ATTR, None)


def get_handlers(plugin: Any) -> Mapping[str, Callable[..., Any]] | None:
    """Return an explicitly registered handler map, if the plugin declares one."""
    handlers = getattr(plugin, HANDLERS_ATTR, None)
    if handlers is None:
        return None
    if not isinstance(handlers, Mapping):  # pragma: no cover - defensive
        raise TypeError(f"{HANDLERS_ATTR} must be a mapping, got {type(handlers).__name__}")
    return handlers
