"""Shared fixtures: a fake plugin context and small IR builders.

The fake context mirrors the daemon's ``PluginContext`` (async ``ir_get``/``ir_read``/
``ir_transact``) and applies real RFC 6902 transactions through ``atomc_core_ir.apply_patch``,
so tests exercise the same write path the daemon uses.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from atomc_core_ir import SystemIR, TxResult, apply_patch

TS = "2026-11-04T00:00:00Z"


class FakeLogger:
    """No-op structured logger capturing records for assertions."""

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


class FakeContext:
    """An in-memory ``PluginContext`` backed by a real ``SystemIR``."""

    def __init__(self, ir: SystemIR, root: Path) -> None:
        self.ir = ir
        self.root = root
        self.logger = FakeLogger()
        self.transactions: list[tuple[str, int, list[dict[str, Any]]]] = []

    @property
    def artifact_root(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def _document(self) -> dict[str, Any]:
        return self.ir.model_dump(mode="json", by_alias=True)

    def _resolve(self, path: str) -> Any:
        if path in ("", "/"):
            return self._document()
        parts = path.strip("/").split("/")
        current: Any = self._document()
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list):
                current = current[int(part)]
            else:
                raise ValueError(f"pointer {path!r} not found")
        return current

    def _node_rev(self, path: str) -> int:
        name = path.strip("/").split("/")[0]
        node = self._document().get(name)
        if node is None:
            raise ValueError(f"node /{name} is not present")
        return int(node.get("_meta", {}).get("rev", 0))

    async def ir_get(self, path: str = "/") -> Any:
        return self._resolve(path)

    async def ir_read(self, path: str = "/") -> dict[str, Any]:
        return {"rev": self._node_rev(path), "value": self._resolve(path)}

    async def ir_transact(self, path: str, base_rev: int, ops: list[dict[str, Any]]) -> TxResult:
        self.ir, result = apply_patch(self.ir, path, base_rev, ops)
        self.transactions.append((path, base_rev, ops))
        return result


def build_ir(**nodes: Any) -> SystemIR:
    """Build a validated ``SystemIR`` from node dicts, adding ``_meta`` and document meta."""
    document: dict[str, Any] = {
        "meta": {
            "project_id": "proj:test",
            "name": "test",
            "created_at": TS,
            "modified_at": TS,
            "rev": 0,
            "atomc_version": "0.1.0",
        }
    }
    for name, value in nodes.items():
        if value is None:
            continue
        node = dict(value)
        node.setdefault("_meta", {"rev": 0})
        document[name] = node
    ir = SystemIR.model_validate(document)
    ir.validate_refs()
    return ir
