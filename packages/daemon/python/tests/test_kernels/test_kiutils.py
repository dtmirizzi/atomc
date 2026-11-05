"""Kiutils adapter: pure-Python board parsing and honest missing-package health."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from atomcd.kernels.errors import KernelUnsupportedOperationError
from atomcd.kernels.health import ProbeResult
from atomcd.kernels.kiutils import KiutilsKernel


class _FakeFootprint:
    def __init__(self, lib_id: str, value: str) -> None:
        self.lib_id = lib_id
        self.value = value


class _FakeBoard:
    def __init__(self) -> None:
        self.footprints = [_FakeFootprint("Switch:SW_MX", "SW1"), _FakeFootprint("Diode:D", "D1")]

    @classmethod
    def from_file(cls, path: str) -> _FakeBoard:
        assert path.endswith(".kicad_pcb")
        return cls()


def _install_fake_kiutils(monkeypatch: pytest.MonkeyPatch) -> None:
    board_module = types.ModuleType("kiutils.board")
    board_module.Board = _FakeBoard  # type: ignore[attr-defined]
    package = types.ModuleType("kiutils")
    package.board = board_module
    monkeypatch.setitem(sys.modules, "kiutils", package)
    monkeypatch.setitem(sys.modules, "kiutils.board", board_module)


def _started_kernel() -> KiutilsKernel:
    kernel = KiutilsKernel()
    kernel._probe = lambda: ProbeResult(available=True, detail="test", version="1.4.8")  # type: ignore[method-assign]
    return kernel


async def test_health_unavailable_without_kiutils(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "atomcd.kernels.kiutils.probe_modules",
        lambda *args, **kwargs: ProbeResult(available=False, detail="missing: kiutils"),
    )
    health = await KiutilsKernel().health()
    assert health.availability == "unavailable"


async def test_load_and_summary_with_fake_board(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_kiutils(monkeypatch)
    board_file = tmp_path / "board.kicad_pcb"
    board_file.write_text("(kicad_pcb)\n")

    kernel = _started_kernel()
    await kernel.start()
    try:
        loaded = await kernel.call("load", path=str(board_file))
        assert loaded["footprint_count"] == 2
        assert loaded["footprints"][0]["value"] == "SW1"
        summary = await kernel.call("summary", path=str(board_file))
        assert summary["footprint_count"] == 2
        with pytest.raises(KernelUnsupportedOperationError):
            await kernel.call("erase")
    finally:
        await kernel.stop()


async def test_load_missing_file_reports_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_kiutils(monkeypatch)
    kernel = _started_kernel()
    await kernel.start()
    try:
        with pytest.raises(FileNotFoundError):
            await kernel.call("load", path=str(tmp_path / "nope.kicad_pcb"))
    finally:
        await kernel.stop()
