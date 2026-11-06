"""Test doubles for the plugin host and vendor adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def resolve_pointer(document: Any, pointer: str) -> Any:
    if pointer in ("", "/"):
        return document
    current = document
    for part in pointer.strip("/").split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            current = current[int(key)]
        elif isinstance(current, dict):
            if key not in current:
                return None
            current = current[key]
        else:
            return None
    return current


@dataclass(frozen=True)
class FakeTxResult:
    new_rev: int
    changed_paths: tuple[str, ...] = ()


@dataclass
class FakeContext:
    ir: dict[str, Any]
    rev: int = 7
    produces: tuple[str, ...] = ("/sourcing",)
    transactions: list[dict[str, Any]] = field(default_factory=list)
    artifact_root: Path = field(default_factory=lambda: Path("."))

    async def ir_read(self, path: str = "/") -> dict[str, Any]:
        return {"rev": self.rev, "value": resolve_pointer(self.ir, path)}

    async def ir_get(self, path: str = "/") -> Any:
        return resolve_pointer(self.ir, path)

    async def ir_transact(
        self,
        path: str,
        base_rev: int,
        ops: list[dict[str, Any]],
    ) -> FakeTxResult:
        if base_rev != self.rev:
            raise ValueError(f"revision conflict: expected {self.rev}, got {base_rev}")
        if not any(path == scope or path.startswith(scope + "/") for scope in self.produces):
            raise PermissionError(f"write outside produces scopes: {path}")
        self.transactions.append({"path": path, "base_rev": base_rev, "ops": ops})
        self.rev += 1
        return FakeTxResult(new_rev=self.rev, changed_paths=(path,))
