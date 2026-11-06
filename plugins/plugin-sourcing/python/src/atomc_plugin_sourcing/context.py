"""Structural type for the host context a sourcing handler receives.

Mirrors the daemon's ``PluginContext`` (async ``ir_get``/``ir_read``/``ir_transact``) without
importing the daemon. Writes always go through ``ir_transact`` so the daemon enforces this
plugin's ``produces`` scope (``/sourcing``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

__all__ = ["PluginContext"]


@runtime_checkable
class PluginContext(Protocol):
    """Capabilities the daemon exposes to a plugin during one invocation."""

    @property
    def artifact_root(self) -> Path:
        """Directory the plugin may write build artifacts into."""
        ...

    @property
    def logger(self) -> Any:
        """Structured, plugin-scoped logger."""
        ...

    async def ir_get(self, path: str = "/") -> Any:
        """Return the IR value at ``path`` (``None`` when a domain node is absent)."""
        ...

    async def ir_read(self, path: str = "/") -> dict[str, Any]:
        """Return ``{rev, value}`` for ``path`` when the host implements revision reads."""
        ...

    async def ir_transact(
        self,
        path: str,
        base_rev: int,
        ops: list[dict[str, Any]],
    ) -> Any:
        """Apply ``ops`` relative to ``path`` under optimistic concurrency control."""
        ...
