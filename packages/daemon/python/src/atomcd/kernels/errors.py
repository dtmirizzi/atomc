"""Exceptions raised by the warm-kernel layer.

Nothing here imports a hardware engine, so this module is always safe to import.
"""

from __future__ import annotations


class KernelError(Exception):
    """Base class for every kernel-layer failure."""


class KernelUnavailableError(KernelError):
    """An optional dependency is missing; the kernel cannot start.

    This is a normal, expected condition in a daemon environment that did not install the
    hardware toolchains. It is *not* an unexpected error, so callers may report it as
    ``unavailable`` rather than ``error``.
    """

    def __init__(self, name: str, detail: str) -> None:
        self.name = name
        self.detail = detail
        super().__init__(f"{name} unavailable: {detail}")


class KernelUnsupportedOperationError(KernelError):
    """The kernel cannot service an operation with any supported public API.

    Raised instead of pretending an operation succeeded. Phase 4 plugins are expected to shell
    out to the vendor CLI (for example ``ato`` or ``qmk``) when no stable Python API exists.
    """

    def __init__(self, name: str, op: str, detail: str) -> None:
        self.name = name
        self.op = op
        self.detail = detail
        super().__init__(f"{name}.{op} unsupported: {detail}")


class WorkerError(KernelError):
    """Base class for supervised worker-process failures."""


class WorkerStartError(WorkerError):
    """The worker process could not be spawned or failed during startup."""


class WorkerCrashedError(WorkerError):
    """The worker process died while a request was outstanding."""


class WorkerTimeoutError(WorkerError):
    """A worker request exceeded its deadline and the worker was terminated."""


class WorkerCallError(WorkerError):
    """The worker returned a structured error for a request."""

    def __init__(self, op: str, kind: str, message: str) -> None:
        self.op = op
        self.kind = kind
        self.message = message
        super().__init__(f"worker op {op!r} failed ({kind}): {message}")


__all__ = [
    "KernelError",
    "KernelUnavailableError",
    "KernelUnsupportedOperationError",
    "WorkerCallError",
    "WorkerCrashedError",
    "WorkerError",
    "WorkerStartError",
    "WorkerTimeoutError",
]
