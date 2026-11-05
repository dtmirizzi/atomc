"""The ``PluginHost`` protocol a plugin is given at runtime.

These are structural types only: nothing here imports daemon internals, so a plugin can be
unit-tested with a fake host and the daemon can satisfy the protocol without a dependency on
``atomc-plugin-sdk`` beyond the protocol definition. Method names and semantics mirror the RPC
contract (``docs/architecture/contracts/rpc.md``): IR reads return a revision-tagged value and
``ir_transact`` applies RFC 6902 operations **relative to** ``path`` under optimistic concurrency.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "CacheLike",
    "EventSink",
    "IrSnapshot",
    "JsonPatchOp",
    "LoggerLike",
    "PluginHost",
    "TransactResult",
]

JsonPatchOp = dict[str, Any]
"""A single RFC 6902 JSON Patch operation (``{"op", "path", ...}``)."""


@dataclass(frozen=True, slots=True)
class IrSnapshot:
    """A revision-tagged IR subtree returned by :meth:`PluginHost.ir_get`."""

    rev: int
    value: Any


@dataclass(frozen=True, slots=True)
class TransactResult:
    """Outcome of :meth:`PluginHost.ir_transact`."""

    new_rev: int
    changed_paths: tuple[str, ...] = field(default_factory=tuple)


@runtime_checkable
class LoggerLike(Protocol):
    """The subset of ``structlog``/stdlib logging the SDK relies on."""

    def debug(self, msg: str, /, **fields: Any) -> None: ...

    def info(self, msg: str, /, **fields: Any) -> None: ...

    def warning(self, msg: str, /, **fields: Any) -> None: ...

    def error(self, msg: str, /, **fields: Any) -> None: ...


@runtime_checkable
class CacheLike(Protocol):
    """A tiny namespaced key/value cache with optional TTL (implemented by the daemon)."""

    def get(self, key: str, /) -> Any | None: ...

    def set(self, key: str, value: Any, /, ttl_s: int | None = None) -> None: ...

    def delete(self, key: str, /) -> None: ...


@runtime_checkable
class EventSink(Protocol):
    """Push notifications to subscribers (``ir.changed``, ``gate.result``, ``dag.*``, ``log``)."""

    def emit(self, topic: str, data: Mapping[str, Any], /) -> None: ...


@runtime_checkable
class PluginHost(Protocol):
    """Capabilities the daemon exposes to a loaded plugin.

    Implementations live in the daemon; third parties only ever consume this protocol.
    """

    @property
    def artifact_root(self) -> Path:
        """Directory the plugin may write build artifacts into (created by the daemon)."""
        ...

    @property
    def logger(self) -> LoggerLike:
        """Structured logger scoped to the plugin."""
        ...

    @property
    def cache(self) -> CacheLike:
        """Namespaced cache for expensive external lookups, with TTL support."""
        ...

    @property
    def events(self) -> EventSink:
        """Event sink for best-effort push notifications."""
        ...

    def ir_get(self, path: str = "/") -> IrSnapshot:
        """Read an IR subtree and its current revision."""
        ...

    def ir_transact(
        self,
        path: str,
        base_rev: int,
        ops: list[JsonPatchOp],
        holder: str | None = None,
    ) -> TransactResult:
        """Apply ``ops`` **relative to** ``path`` against ``base_rev``.

        Raises on revision conflict, lock conflict or IR validation failure; on failure the IR
        and its revisions are unchanged.
        """
        ...
