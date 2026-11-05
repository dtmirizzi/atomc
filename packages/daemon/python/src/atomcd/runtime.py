"""Persistent runtime state at ``~/.atomc/daemon.json`` (mode ``0600``).

Implements the lifecycle rules in ``docs/architecture/contracts/rpc.md``: atomic write with
restrictive permissions, stale-pid cleanup on start, and cleanup on shutdown. The token is
never logged.
"""

from __future__ import annotations

import contextlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict

from .common import atomic_write_text, utcnow_iso


class DaemonState(BaseModel):
    """The contents of ``daemon.json``."""

    model_config = ConfigDict(extra="forbid")

    pid: int
    host: str
    port: int
    token: str
    project_root: str
    started_at: str
    version: str


def pid_alive(pid: int) -> bool:
    """Return True if a process with ``pid`` currently exists (signal 0 probe)."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but owned by another user
    return True


class RuntimeState:
    """Read/write access to the daemon runtime file under ``state_dir``."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.path = state_dir / "daemon.json"

    def read(self) -> DaemonState | None:
        """Read the state file, returning ``None`` when absent."""
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        return DaemonState.model_validate_json(raw)

    def write(
        self,
        *,
        pid: int,
        host: str,
        port: int,
        token: str,
        project_root: str,
        version: str,
        started_at: str | None = None,
    ) -> DaemonState:
        """Atomically write the state file with mode ``0600`` and return it."""
        state = DaemonState(
            pid=pid,
            host=host,
            port=port,
            token=token,
            project_root=project_root,
            started_at=started_at or utcnow_iso(),
            version=version,
        )
        atomic_write_text(self.path, state.model_dump_json(), mode=0o600)
        return state

    def clear(self) -> None:
        """Remove the state file if present (never raises on absence)."""
        with contextlib.suppress(FileNotFoundError):
            self.path.unlink()

    def clear_if_stale(self) -> bool:
        """Delete the state file when its pid is dead. Returns True if cleared."""
        state = self.read()
        if state is None:
            return False
        if pid_alive(state.pid):
            return False
        self.clear()
        return True

    def age_ms(self, now: datetime | None = None) -> int | None:
        """Milliseconds since ``started_at``, or ``None`` when no state file exists."""
        state = self.read()
        if state is None:
            return None
        started = datetime.fromisoformat(state.started_at.replace("Z", "+00:00"))
        current = now or datetime.now(UTC)
        return max(0, int((current - started).total_seconds() * 1000))


def load_state_file(path: Path) -> dict[str, Any] | None:
    """Load an arbitrary daemon state JSON file, used by the CLI ``status``/``stop``."""
    try:
        return cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return None


__all__ = [
    "DaemonState",
    "RuntimeState",
    "load_state_file",
    "pid_alive",
]
