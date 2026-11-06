"""Subprocess abstraction for the ``ato`` CLI.

atopile 0.15 has no supported build API (see ``atomcd.kernels.atopile``), so compilation shells
out to ``ato build``. The runner is injectable so tests exercise PASS/FAIL/timeout outcomes
without a real toolchain while production code always traces to a real process exit code.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

__all__ = [
    "CommandResult",
    "CommandRunner",
    "SubprocessRunner",
    "bounded",
    "find_ato",
]

_MAX_OUTPUT_CHARS = 8000


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Outcome of one external command invocation."""

    returncode: int
    stdout: str = ""
    stderr: str = ""


class CommandRunner(Protocol):
    """Runs an external command and captures bounded output."""

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        timeout_s: int,
    ) -> CommandResult: ...


class SubprocessRunner:
    """Default runner backed by :mod:`subprocess`."""

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        timeout_s: int,
    ) -> CommandResult:
        try:
            completed = subprocess.run(
                list(argv),
                cwd=str(cwd),
                timeout=timeout_s,
                capture_output=True,
                text=True,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = _as_text(exc.stdout)
            stderr = _as_text(exc.stderr)
            return CommandResult(
                returncode=124,
                stdout=bounded(stdout),
                stderr=bounded(f"{stderr}\ncommand timed out after {timeout_s}s".strip()),
            )
        except OSError as exc:
            return CommandResult(returncode=127, stderr=f"failed to execute {argv[0]!r}: {exc}")
        return CommandResult(
            returncode=completed.returncode,
            stdout=bounded(completed.stdout or ""),
            stderr=bounded(completed.stderr or ""),
        )


def _as_text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def bounded(text: str, limit: int = _MAX_OUTPUT_CHARS) -> str:
    """Keep the head and tail of ``text`` so evidence stays small but diagnostic."""
    if len(text) <= limit:
        return text
    half = max(limit // 2 - 16, 1)
    omitted = len(text) - 2 * half
    return f"{text[:half]}\n... [{omitted} chars omitted] ...\n{text[-half:]}"


def find_ato(which: Callable[[str], str | None] = shutil.which) -> str | None:
    """Return the path to the ``ato`` CLI, or ``None`` when it is not on ``PATH``."""
    return which("ato")
