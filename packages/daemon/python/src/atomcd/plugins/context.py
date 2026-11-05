"""The plugin host context exposed to plugin gate/tool/watch handlers.

Mirrors the ``PluginHost`` protocol in the plugin-manifest contract (WP-2.2): IR read/transact,
artifact root, logger, cache and events. A context is created per invocation with the caller's
``holder`` identity and enforces the plugin's declared ``produces`` scopes on every write.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from atomc_core_ir import TxResult

from ..ir_store import IRStore

LOGGER = logging.getLogger("atomcd.plugin")


class ScopeError(PermissionError):
    """A plugin attempted to write outside its declared ``produces`` scopes."""


def pointer_allowed(produces: list[str], path: str) -> bool:
    """Return True when ``path`` falls under one of the ``produces`` JSON pointers.

    A scope covers itself and any descendant: ``/sourcing`` covers ``/sourcing`` and
    ``/sourcing/bom`` but not ``/sourcing2``.
    """
    normalized = "/" + path.strip("/")
    for scope in produces:
        base = "/" + scope.strip("/")
        if normalized == base or normalized.startswith(base + "/"):
            return True
    return False


class PluginContext:
    """Host services handed to a plugin handler for one invocation."""

    def __init__(
        self,
        *,
        plugin_name: str,
        holder: str,
        store: IRStore,
        produces: list[str],
        artifact_root: Path,
        cache: dict[str, Any],
        logger: Any | None = None,
        events: Any | None = None,
    ) -> None:
        self.plugin_name = plugin_name
        self.holder = holder
        self.store = store
        self.produces = list(produces)
        self.artifact_root = artifact_root
        self.cache = cache
        self.logger = logger if logger is not None else LOGGER
        self.events = events

    async def ir_get(self, path: str = "/") -> Any:
        """Read the IR subtree at ``path`` (returns just the value)."""
        _rev, value = self.store.read(path)
        return value

    async def ir_read(self, path: str = "/") -> dict[str, Any]:
        """Read the IR subtree with its revision: ``{rev, value}``."""
        rev, value = self.store.read(path)
        return {"rev": rev, "value": value}

    async def ir_transact(
        self,
        path: str,
        base_rev: int,
        ops: list[dict[str, Any]],
    ) -> TxResult:
        """Apply a transaction, enforcing the plugin's ``produces`` scopes."""
        if not pointer_allowed(self.produces, path):
            raise ScopeError(
                f"plugin {self.plugin_name!r} may not write {path!r}; "
                f"declared produces: {self.produces}"
            )
        return await self.store.transact(path, base_rev, ops, holder=self.holder)

    def artifact_path(self, *parts: str) -> Path:
        """Resolve a path under the plugin's artifact directory (created lazily by writers)."""
        root = self.artifact_root
        for part in parts:
            if part.startswith("/") or ".." in part.split("/"):
                raise ScopeError(f"artifact path part {part!r} must be relative and contained")
            root = root / part
        return root


__all__ = ["PluginContext", "ScopeError", "pointer_allowed"]
