"""Renode/pyrenode3 adapter: env rules, fake engine lifecycle, honest capability reporting."""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest
from atomcd.kernels.errors import (
    KernelError,
    KernelUnavailableError,
    KernelUnsupportedOperationError,
)
from atomcd.kernels.health import ProbeResult
from atomcd.kernels.renode import (
    RenodeKernel,
    deprecated_aliases,
    resolve_renode_path,
)


class _FakeMachine:
    def __init__(self, name: str) -> None:
        self.name = name
        self.repls: list[str] = []

    def load_repl(self, path: str) -> None:
        self.repls.append(path)


class _FakeEmulation:
    def __init__(self) -> None:
        self.machines: dict[str, _FakeMachine] = {}

    def add_mach(self, name: str) -> _FakeMachine:
        machine = _FakeMachine(name)
        self.machines[name] = machine
        return machine


class _FakeMonitor:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def execute(self, command: str) -> None:
        self.commands.append(command)


def _install_fake_pyrenode(monkeypatch: pytest.MonkeyPatch) -> None:
    package = types.ModuleType("pyrenode3")
    wrappers = types.ModuleType("pyrenode3.wrappers")
    wrappers.Emulation = _FakeEmulation  # type: ignore[attr-defined]
    wrappers.Monitor = _FakeMonitor  # type: ignore[attr-defined]
    package.wrappers = wrappers
    monkeypatch.setitem(sys.modules, "pyrenode3", package)
    monkeypatch.setitem(sys.modules, "pyrenode3.wrappers", wrappers)


def test_resolve_requires_path() -> None:
    with pytest.raises(KernelUnavailableError):
        resolve_renode_path({})


def test_resolve_returns_env_path() -> None:
    assert resolve_renode_path({"PYRENODE_PATH": "/opt/renode"}) == "/opt/renode"


def test_resolve_rejects_deprecated_aliases() -> None:
    with pytest.raises(KernelError):
        resolve_renode_path({"PYRENODE_PATH": "/opt/renode", "PYRENODE_BIN": "/other"})


def test_deprecated_aliases_detection() -> None:
    assert deprecated_aliases({"PYRENODE_PKG": "x"}) == ["PYRENODE_PKG"]
    assert deprecated_aliases({"PYRENODE_PATH": "/x"}) == []


async def test_probe_reports_missing_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYRENODE_PATH", raising=False)
    kernel = RenodeKernel()
    health = await kernel.health()
    assert health.availability == "unavailable"
    assert health.detail is not None
    assert "PYRENODE_PATH is not set" in health.detail


async def test_probe_reports_dangling_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYRENODE_PATH", "/definitely/not/here")
    kernel = RenodeKernel()
    health = await kernel.health()
    assert health.availability == "unavailable"
    assert health.detail is not None
    assert "does not exist" in health.detail


async def test_start_and_monitor_ops_with_fake_engine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    binary = tmp_path / "Renode"
    binary.write_text("#!/bin/sh\n")
    monkeypatch.setenv("PYRENODE_PATH", str(binary))
    monkeypatch.delenv("PYRENODE_BIN", raising=False)
    monkeypatch.delenv("PYRENODE_PKG", raising=False)
    _install_fake_pyrenode(monkeypatch)

    kernel = RenodeKernel()
    kernel._probe = lambda: ProbeResult(available=True, detail="test", version="0")  # type: ignore[method-assign]
    await kernel.start()
    monitor = kernel._monitor
    try:
        assert await kernel.call("add_machine", name="f4") == {"machine": "f4"}
        assert await kernel.call("load_repl", name="f4", path="@platforms/f4.repl") == {
            "machine": "f4",
            "repl": "@platforms/f4.repl",
        }
        await kernel.call("start")
        await kernel.call("execute", command="echo hi")
        version = await kernel.call("version")
        assert version["path"] is None
        with pytest.raises(KernelUnsupportedOperationError):
            await kernel.call("bogus")
    finally:
        await kernel.stop()
    assert monitor is not None
    assert "start" in monitor.commands
    assert "echo hi" in monitor.commands
    assert "quit" in monitor.commands


async def test_override_sets_only_pyrenode_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    binary = tmp_path / "Renode"
    binary.write_text("#!/bin/sh\n")
    monkeypatch.delenv("PYRENODE_PATH", raising=False)
    monkeypatch.delenv("PYRENODE_BIN", raising=False)
    monkeypatch.delenv("PYRENODE_PKG", raising=False)
    _install_fake_pyrenode(monkeypatch)

    kernel = RenodeKernel(path=str(binary))
    kernel._probe = lambda: ProbeResult(available=True, detail="test", version="0")  # type: ignore[method-assign]
    await kernel.start()
    try:
        assert os.environ["PYRENODE_PATH"] == str(binary)
        assert "PYRENODE_BIN" not in os.environ
        assert "PYRENODE_PKG" not in os.environ
    finally:
        await kernel.stop()
