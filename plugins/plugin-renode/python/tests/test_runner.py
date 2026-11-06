"""Runner tests: binary resolution, command shape and subprocess behaviour."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from atomc_plugin_renode.runner import (
    RENODE_ENV_VARS,
    SubprocessRenodeRunner,
    find_renode_binary,
    headless_args,
)


def test_env_override_wins(tmp_path: Path) -> None:
    binary = tmp_path / "renode"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    for name in RENODE_ENV_VARS:
        resolved = find_renode_binary({name: str(binary)}, known_locations=[])
        assert resolved == str(binary)


def test_missing_binary_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Force PATH lookup to miss and disable known locations.
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert find_renode_binary({}, known_locations=[]) is None


def test_known_location_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary = tmp_path / "renode"
    binary.write_text("", encoding="utf-8")
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert find_renode_binary({}, known_locations=[str(binary)]) == str(binary)


def test_headless_args_shape() -> None:
    args = headless_args("/opt/renode", Path("/tmp/boot.resc"))
    assert args[0] == "/opt/renode"
    assert "--disable-gui" in args
    assert "--plain" in args
    assert args[-1] == "/tmp/boot.resc"
    assert args[-3:-1] == ["--port", "-1"]


def test_subprocess_runner_captures_output(tmp_path: Path) -> None:
    runner = SubprocessRenodeRunner(sys.executable)
    result = runner.run(
        [sys.executable, "-c", "print('hello-renode')"],
        timeout_s=10,
        cwd=tmp_path,
    )
    assert result.exit_code == 0
    assert not result.timed_out
    assert "hello-renode" in result.stdout


def test_subprocess_runner_times_out(tmp_path: Path) -> None:
    runner = SubprocessRenodeRunner(sys.executable)
    result = runner.run(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        timeout_s=0.3,
        cwd=tmp_path,
    )
    assert result.timed_out
    assert result.exit_code is None
