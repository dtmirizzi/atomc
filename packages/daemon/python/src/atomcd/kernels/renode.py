"""pyrenode3 / Renode adapter.

Renode is driven through the released ``pyrenode3`` package, which reads **only**
``PYRENODE_PATH`` (see ``docs/plan/ENVIRONMENT.md`` §2). The deprecated ``PYRENODE_BIN`` /
``PYRENODE_PKG`` aliases are never set or combined; if a caller has them in the environment the
adapter reports a clear error during startup rather than letting pythonnet raise an opaque
``ImportError``.

Health and startup are honest about capability: a missing Renode binary or an uninstalled
``pyrenode3`` yields ``unavailable``, never a fake PASS.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from atomcd.kernels.base import BaseKernel
from atomcd.kernels.errors import (
    KernelError,
    KernelUnavailableError,
    KernelUnsupportedOperationError,
)
from atomcd.kernels.health import ProbeResult
from atomcd.kernels.importer import import_module, module_available, module_version

RENODE_PATH_ENV = "PYRENODE_PATH"
DEPRECATED_PATH_ENV = ("PYRENODE_BIN", "PYRENODE_PKG")


def deprecated_aliases(environ: Mapping[str, str]) -> list[str]:
    """Return any deprecated Renode path variables that are set."""
    return [name for name in DEPRECATED_PATH_ENV if environ.get(name)]


def resolve_renode_path(
    environ: Mapping[str, str] | None = None,
    *,
    override: str | None = None,
) -> str:
    """Resolve the Renode binary path, honouring only ``PYRENODE_PATH``."""
    env = os.environ if environ is None else environ
    aliases = deprecated_aliases(env)
    if aliases:
        raise KernelError(
            f"deprecated Renode path variables are set ({', '.join(aliases)}); "
            f"pyrenode3 requires only {RENODE_PATH_ENV}"
        )
    path = override or env.get(RENODE_PATH_ENV)
    if not path:
        raise KernelUnavailableError("renode", f"{RENODE_PATH_ENV} is not set")
    return path


class RenodeKernel(BaseKernel):
    """Start/stop pyrenode3 and execute Renode monitor commands."""

    def __init__(self, *, path: str | None = None) -> None:
        super().__init__("renode", package="pyrenode3")
        self._path = path
        self._emulation: Any = None
        self._monitor: Any = None
        self._machines: dict[str, Any] = {}

    def _probe(self) -> ProbeResult:
        problems: list[str] = []
        aliases = deprecated_aliases(os.environ)
        if aliases:
            problems.append(f"deprecated env vars set: {', '.join(aliases)}")
        path = self._path or os.environ.get(RENODE_PATH_ENV)
        if not path:
            problems.append(f"{RENODE_PATH_ENV} is not set")
        elif not Path(path).exists():
            problems.append(f"{RENODE_PATH_ENV} does not exist: {path}")
        if not module_available("pyrenode3"):
            problems.append("pyrenode3 is not installed")
        if problems:
            return ProbeResult(available=False, detail="; ".join(problems))
        return ProbeResult(
            available=True,
            detail=f"renode at {path}",
            version=module_version("pyrenode3"),
        )

    async def _start(self) -> None:
        path = resolve_renode_path(override=self._path)
        if not Path(path).exists():
            raise KernelUnavailableError(self.name, f"{RENODE_PATH_ENV} does not exist: {path}")
        if self._path and not os.environ.get(RENODE_PATH_ENV):
            # Only PYRENODE_PATH is ever written; callers with the deprecated aliases already
            # failed in resolve_renode_path.
            os.environ[RENODE_PATH_ENV] = self._path
        import_module("pyrenode3")
        wrappers = import_module("pyrenode3.wrappers")
        self._emulation = wrappers.Emulation()
        self._monitor = wrappers.Monitor()

    async def _stop(self) -> None:
        monitor = self._monitor
        if monitor is not None:
            with contextlib.suppress(Exception):
                monitor.execute("quit")
        self._machines.clear()
        self._emulation = None
        self._monitor = None

    async def _call(self, op: str, **kwargs: Any) -> Any:
        if op == "version":
            return {"pyrenode3": self._version, "path": self._path}
        if op == "add_machine":
            return self._add_machine(str(kwargs["name"]))
        if op == "load_repl":
            return self._load_repl(str(kwargs["name"]), str(kwargs["path"]))
        if op in ("start", "pause", "reset", "quit", "shutdown"):
            return self._monitor_command(op)
        if op == "execute":
            return self._monitor_command(str(kwargs["command"]))
        raise KernelUnsupportedOperationError(
            self.name,
            op,
            "supported ops: version, add_machine, load_repl, start, pause, reset, quit, execute",
        )

    def _add_machine(self, name: str) -> dict[str, Any]:
        machine = self._emulation.add_mach(name)
        self._machines[name] = machine
        return {"machine": name}

    def _load_repl(self, name: str, path: str) -> dict[str, Any]:
        machine = self._machines.get(name)
        if machine is None:
            raise KeyError(f"unknown machine {name!r}; call add_machine first")
        machine.load_repl(path)
        return {"machine": name, "repl": path}

    def _monitor_command(self, command: str) -> str:
        result = self._monitor.execute(command)
        return "" if result is None else str(result)


__all__ = [
    "DEPRECATED_PATH_ENV",
    "RENODE_PATH_ENV",
    "RenodeKernel",
    "deprecated_aliases",
    "resolve_renode_path",
]
