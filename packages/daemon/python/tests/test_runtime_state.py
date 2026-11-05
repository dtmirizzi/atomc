"""Runtime state file lifecycle: pid probing, stale cleanup, age and loading."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from atomcd.common import atomic_write_text
from atomcd.runtime import RuntimeState, load_state_file, pid_alive

STATE = {
    "pid": 4321,
    "host": "127.0.0.1",
    "port": 7437,
    "token": "secret",
    "project_root": "/tmp/project",
    "started_at": "2026-11-04T00:00:00Z",
    "version": "0.0.1",
}


def test_pid_alive_of_current_process() -> None:
    assert pid_alive(os.getpid()) is True


def test_pid_alive_rejects_invalid() -> None:
    assert pid_alive(0) is False
    assert pid_alive(-1) is False


def test_read_missing_returns_none(tmp_path: Path) -> None:
    assert RuntimeState(tmp_path).read() is None


def test_write_read_and_clear(tmp_path: Path) -> None:
    state = RuntimeState(tmp_path)
    written = state.write(
        pid=111,
        host="127.0.0.1",
        port=1234,
        token="t",
        project_root="/p",
        version="0.0.1",
        started_at="2026-11-04T00:00:00Z",
    )
    assert written.pid == 111
    assert state.read() is not None
    assert (state.path.stat().st_mode & 0o777) == 0o600
    state.clear()
    state.clear()  # idempotent
    assert state.read() is None


def test_clear_if_stale_removes_dead_pid(tmp_path: Path) -> None:
    state = RuntimeState(tmp_path)
    state.write(
        pid=999999,
        host="h",
        port=1,
        token="t",
        project_root="/p",
        version="v",
    )
    assert state.clear_if_stale() is True
    assert state.read() is None


def test_clear_if_stale_keeps_live_pid(tmp_path: Path) -> None:
    state = RuntimeState(tmp_path)
    state.write(
        pid=os.getpid(),
        host="h",
        port=1,
        token="t",
        project_root="/p",
        version="v",
    )
    assert state.clear_if_stale() is False
    assert state.read() is not None


def test_age_ms(tmp_path: Path) -> None:
    state = RuntimeState(tmp_path)
    started = datetime.now(UTC) - timedelta(seconds=5)
    state.write(
        pid=1,
        host="h",
        port=1,
        token="t",
        project_root="/p",
        version="v",
        started_at=started.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    age = state.age_ms()
    assert age is not None
    assert age >= 4000


def test_load_state_file(tmp_path: Path) -> None:
    path = tmp_path / "daemon.json"
    atomic_write_text(path, json.dumps(STATE))
    loaded = load_state_file(path)
    assert loaded is not None
    assert loaded["pid"] == 4321
    assert load_state_file(tmp_path / "missing.json") is None
