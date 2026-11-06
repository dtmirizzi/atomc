"""Renode process execution.

The plugin drives Renode as a headless subprocess. Renode 1.17.0 has no ``--console`` flag; the
headless invocation used here is ``renode --disable-gui --plain --port -1 <script>`` run with a
hard subprocess timeout. A missing binary is reported honestly (``None``) so gates can ``SKIP``
rather than pretend to run.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

__all__ = [
    "RENODE_ENV_VARS",
    "RenodeRunResult",
    "RenodeRunner",
    "SubprocessRenodeRunner",
    "find_renode_binary",
    "headless_args",
]

RENODE_ENV_VARS = ("ATOMC_RENODE_BIN", "PYRENODE_PATH")
"""Environment variables consulted for an explicit Renode binary path (in order)."""

_KNOWN_LOCATIONS = (
    "~/.local/opt/renode-1.17.0/Renode.app/Contents/MacOS/renode",
    "/Applications/Renode.app/Contents/MacOS/renode",
)
"""Common install locations, checked after ``PATH``."""


@dataclass(frozen=True, slots=True)
class RenodeRunResult:
    """Outcome of one Renode invocation."""

    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int

    @property
    def combined_output(self) -> str:
        return f"{self.stdout}\n{self.stderr}"


class RenodeRunner(Protocol):
    """Executes a generated ``.resc`` script and returns captured output."""

    def run(
        self,
        args: Sequence[str],
        *,
        timeout_s: float,
        cwd: Path,
    ) -> RenodeRunResult: ...


def find_renode_binary(
    environ: Mapping[str, str] | None = None,
    *,
    known_locations: Sequence[str] | None = None,
) -> str | None:
    """Resolve the Renode executable, or ``None`` when it is not installed.

    Order: explicit ``ATOMC_RENODE_BIN`` / ``PYRENODE_PATH``, then ``PATH``, then the common
    macOS portable/app locations.
    """
    env = os.environ if environ is None else environ
    for name in RENODE_ENV_VARS:
        env_value = env.get(name)
        if env_value and Path(env_value).is_file():
            return env_value
    found = shutil.which("renode")
    if found:
        return found
    for location in known_locations if known_locations is not None else _KNOWN_LOCATIONS:
        candidate = Path(location).expanduser()
        if candidate.is_file():
            return str(candidate)
    return None


def headless_args(binary: str, script: Path) -> list[str]:
    """Build the deterministic headless Renode command line for ``script``."""
    return [binary, "--disable-gui", "--plain", "--port", "-1", str(script)]


class SubprocessRenodeRunner:
    """Default :class:`RenodeRunner` backed by :mod:`subprocess`."""

    def __init__(self, binary: str) -> None:
        self.binary = binary

    def run(
        self,
        args: Sequence[str],
        *,
        timeout_s: float,
        cwd: Path,
    ) -> RenodeRunResult:
        import time

        started = time.perf_counter()
        try:
            completed = subprocess.run(
                list(args),
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return RenodeRunResult(
                exit_code=None,
                stdout=_as_text(exc.stdout),
                stderr=_as_text(exc.stderr),
                timed_out=True,
                duration_ms=duration_ms,
            )
        duration_ms = int((time.perf_counter() - started) * 1000)
        return RenodeRunResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            timed_out=False,
            duration_ms=duration_ms,
        )


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
