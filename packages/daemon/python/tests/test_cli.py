"""``atomcd`` CLI: doctor, status, stop and the serve lifecycle (uvicorn stubbed)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from atomcd.cli import _build_services, app
from atomcd.config import DaemonConfig
from atomcd.runtime import RuntimeState
from typer.testing import CliRunner

runner = CliRunner()


def write_state(state_dir: Path, pid: int, *, port: int = 1) -> None:
    # Port 1 is reserved and never listening locally: the status health check
    # must fail regardless of any real daemon the developer happens to run on
    # the default port (7437).
    RuntimeState(state_dir).write(
        pid=pid,
        host="127.0.0.1",
        port=port,
        token="t",
        project_root="/tmp/project",
        version="0.0.1",
    )


def test_doctor_reports_ok() -> None:
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert any(check["name"] == "core-ir import" for check in payload["checks"])


def test_doctor_human_output() -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "[ok] python" in result.stdout


def test_status_no_daemon(tmp_path: Path) -> None:
    result = runner.invoke(app, ["status", "--state-dir", str(tmp_path), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["running"] is False
    assert payload["error"] == "no daemon.json"


def test_status_with_stale_pid(tmp_path: Path) -> None:
    write_state(tmp_path, 999999)
    result = runner.invoke(app, ["status", "--state-dir", str(tmp_path), "--json"])
    payload = json.loads(result.stdout)
    assert payload["running"] is False
    assert payload["pid_alive"] is False
    assert "health_error" in payload


def test_stop_no_daemon(tmp_path: Path) -> None:
    result = runner.invoke(app, ["stop", "--state-dir", str(tmp_path), "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["stopped"] is False


def test_stop_stale_pid(tmp_path: Path) -> None:
    write_state(tmp_path, 999999)
    result = runner.invoke(app, ["stop", "--state-dir", str(tmp_path), "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["reason"] == "stale pid removed"
    assert RuntimeState(tmp_path).read() is None


def test_stop_running_pid(tmp_path: Path, monkeypatch: Any) -> None:
    write_state(tmp_path, os.getpid())
    calls = {"n": 0}

    def fake_alive(pid: int) -> bool:
        calls["n"] += 1
        return calls["n"] == 1

    monkeypatch.setattr("atomcd.cli.pid_alive", fake_alive)
    monkeypatch.setattr("atomcd.cli.os.kill", lambda pid, sig: None)
    result = runner.invoke(app, ["stop", "--state-dir", str(tmp_path), "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["stopped"] is True
    assert RuntimeState(tmp_path).read() is None


def test_serve_refuses_when_already_running(tmp_path: Path) -> None:
    write_state(tmp_path, 1)  # a live pid that is not this process
    result = runner.invoke(
        app,
        ["serve", "--project", str(tmp_path), "--state-dir", str(tmp_path), "--json"],
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"] == "daemon already running"


class FakeServer:
    def __init__(self, config: Any) -> None:
        self.config = config
        self.should_exit = False

    async def serve(self) -> None:
        return


def test_serve_start_and_cleanup(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr("atomcd.cli.uvicorn.Server", FakeServer)
    state_dir = tmp_path / "state"
    result = runner.invoke(
        app,
        ["serve", "--project", str(tmp_path), "--state-dir", str(state_dir), "--json"],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["ok"] is True
    # The pid file is removed on graceful shutdown.
    assert RuntimeState(state_dir).read() is None


def test_build_services_wires_components(tmp_path: Path) -> None:
    config = DaemonConfig(project_root=tmp_path, state_dir=tmp_path / "state", token="t")
    services = _build_services(config)
    assert services.store.rev == 0
    assert services.plugins is not None
    assert services.gates is not None
    assert services.dag is not None
