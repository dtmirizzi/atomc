"""Shared fixtures for the cad-jig plugin tests."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "atomc_pad.ir.json"


@pytest.fixture
def atomc_pad_ir() -> dict[str, Any]:
    """The committed atomc-pad IR fixture as a mutable copy."""
    return copy.deepcopy(json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))


def _resolve(document: Mapping[str, Any], path: str) -> Any:
    node: Any = document
    for part in path.strip("/").split("/"):
        if not part:
            continue
        node = node[part]
    return node


class FakeContext:
    """A minimal daemon-like :class:`PluginContext` for handler tests."""

    def __init__(self, ir: Mapping[str, Any], artifact_root: Path, rev: int = 7) -> None:
        self.ir = ir
        self.rev = rev
        self.artifact_root = artifact_root
        self.transactions: list[tuple[str, int, list[dict[str, Any]]]] = []

    async def ir_get(self, path: str = "/") -> Any:
        return _resolve(self.ir, path)

    async def ir_read(self, path: str = "/") -> dict[str, Any]:
        return {"rev": self.rev, "value": _resolve(self.ir, path)}

    async def ir_transact(
        self, path: str, base_rev: int, ops: list[dict[str, Any]]
    ) -> SimpleNamespace:
        self.transactions.append((path, base_rev, ops))
        self.rev += 1
        return SimpleNamespace(new_rev=self.rev, changed_paths=(path,))

    def artifact_path(self, *parts: str) -> Path:
        root = self.artifact_root
        for part in parts:
            root = root / part
        return root


@pytest.fixture
def ctx(atomc_pad_ir: dict[str, Any], tmp_path: Path) -> FakeContext:
    return FakeContext(atomc_pad_ir, tmp_path)
