"""Shared fixtures: a realistic IR document, a fake host context and a fake Renode runner."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from atomc_plugin_renode.runner import RenodeRunResult

FIXTURES = Path(__file__).parent / "fixtures"
GOLDENS = Path(__file__).parent / "goldens"


@pytest.fixture
def goldens() -> Path:
    return GOLDENS


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def fixture_doc() -> dict[str, Any]:
    return json.loads((FIXTURES / "atomc_pad_ir.json").read_text(encoding="utf-8"))


class FakeContext:
    """Async stand-in for the daemon's ``PluginContext``."""

    def __init__(self, ir: dict[str, Any], root: Path, artifact_root: Path) -> None:
        self._ir = ir
        self.root = root
        self._artifact_root = artifact_root
        self.transactions: list[tuple[str, int, list[dict[str, Any]]]] = []
        self.revs: dict[str, int] = {"/simulation": 3, "/firmware": 3}

    @property
    def artifact_root(self) -> Path:
        self._artifact_root.mkdir(parents=True, exist_ok=True)
        return self._artifact_root

    async def ir_get(self, path: str = "/") -> Any:
        if path in ("/", ""):
            return self._ir
        node = path.strip("/")
        if node in self._ir and isinstance(self._ir[node], dict):
            return self._ir[node]
        raise KeyError(path)

    async def ir_read(self, path: str = "/") -> dict[str, Any]:
        node = path.strip("/").split("/")[0]
        if node not in self._ir:
            raise KeyError(path)
        return {"rev": self.revs.get(f"/{node}", 0), "value": self._ir[node]}

    async def ir_transact(self, path: str, base_rev: int, ops: list[dict[str, Any]]) -> None:
        self.transactions.append((path, base_rev, ops))


@dataclass
class FakeRunner:
    """Records the command and returns a canned :class:`RenodeRunResult`."""

    result: RenodeRunResult
    calls: list[tuple[list[str], float, Path]] = field(default_factory=list)

    def run(self, args: list[str], *, timeout_s: float, cwd: Path) -> RenodeRunResult:
        self.calls.append((list(args), timeout_s, cwd))
        return self.result


@pytest.fixture
def make_runner() -> Any:
    def _make(result: RenodeRunResult) -> FakeRunner:
        return FakeRunner(result=result)

    return _make


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "system_ir.json").write_text("{}\n", encoding="utf-8")
    return root


@pytest.fixture
def fake_ctx(fixture_doc: dict[str, Any], project_root: Path) -> FakeContext:
    return FakeContext(
        ir=fixture_doc,
        root=project_root,
        artifact_root=project_root / ".atomc" / "artifacts" / "renode",
    )
