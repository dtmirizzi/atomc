"""A minimal in-memory :class:`~atomc_plugin_sdk.host.PluginHost` for tests and examples.

Plugins can be developed and unit-tested with no daemon running. This fake records transactions
and events so tests can assert on them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .host import IrSnapshot, TransactResult

__all__ = ["FakePluginHost", "RecordedTransact"]


@dataclass(frozen=True, slots=True)
class RecordedTransact:
    path: str
    base_rev: int
    ops: tuple[dict[str, Any], ...]
    holder: str | None


class _FakeLogger:
    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict[str, Any]]] = []

    def _log(self, level: str, msg: str, **fields: Any) -> None:
        self.records.append((level, msg, fields))

    def debug(self, msg: str, /, **fields: Any) -> None:
        self._log("debug", msg, **fields)

    def info(self, msg: str, /, **fields: Any) -> None:
        self._log("info", msg, **fields)

    def warning(self, msg: str, /, **fields: Any) -> None:
        self._log("warning", msg, **fields)

    def error(self, msg: str, /, **fields: Any) -> None:
        self._log("error", msg, **fields)


class _FakeCache:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    def get(self, key: str, /) -> Any | None:
        return self.store.get(key)

    def set(self, key: str, value: Any, /, ttl_s: int | None = None) -> None:
        del ttl_s
        self.store[key] = value

    def delete(self, key: str, /) -> None:
        self.store.pop(key, None)


@dataclass
class FakePluginHost:
    """In-memory host used in tests. Satisfies the structural ``PluginHost`` protocol."""

    root: Path
    ir: dict[str, Any] = field(default_factory=dict)
    rev: int = 0
    events: list[tuple[str, Mapping[str, Any]]] = field(default_factory=list)
    transactions: list[RecordedTransact] = field(default_factory=list)
    logger: _FakeLogger = field(default_factory=_FakeLogger)
    cache: _FakeCache = field(default_factory=_FakeCache)

    @property
    def artifact_root(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def emit(self, topic: str, data: Mapping[str, Any], /) -> None:
        self.events.append((topic, dict(data)))

    def ir_get(self, path: str = "/") -> IrSnapshot:
        return IrSnapshot(rev=self.rev, value=self.ir)

    def ir_transact(
        self,
        path: str,
        base_rev: int,
        ops: list[dict[str, Any]],
        holder: str | None = None,
    ) -> TransactResult:
        if base_rev != self.rev:
            raise ValueError(f"revision conflict: current {self.rev}, expected {base_rev}")
        self.transactions.append(
            RecordedTransact(path=path, base_rev=base_rev, ops=tuple(ops), holder=holder)
        )
        self.rev += 1
        return TransactResult(new_rev=self.rev, changed_paths=(path,))
