"""Warm hardware-kernel registry for ``atomcd`` (WP-2.4).

Import-safety contract: ``import atomcd.kernels`` must not import atopile, faebryk, OCP,
build123d, pythonnet/pyrenode3 or kiutils, and must not spawn any process. Every heavy import
happens inside a kernel's ``_start``; CAD additionally runs in a separately spawned worker
process. A daemon environment without any hardware engine installed can still import this package
and report every kernel as ``unavailable``.

The public surface is deliberately small:

* :class:`DefaultKernelRegistry` — implements ``atomcd.kernel_protocol.KernelRegistry``;
* :class:`BaseKernel` — lifecycle base for adapters;
* :class:`KernelHealthSnapshot` — health/availability/version/cold-warm/restart reporting;
* :func:`create_default_registry` — lazily registered built-ins (atopile, kiutils, ocp, renode).
"""

from __future__ import annotations

from atomcd.kernels.base import BaseKernel
from atomcd.kernels.errors import (
    KernelError,
    KernelUnavailableError,
    KernelUnsupportedOperationError,
    WorkerCallError,
    WorkerCrashedError,
    WorkerError,
    WorkerStartError,
    WorkerTimeoutError,
)
from atomcd.kernels.health import Availability, KernelHealthSnapshot, ProbeResult
from atomcd.kernels.registry import DefaultKernelRegistry

__all__ = [
    "Availability",
    "BaseKernel",
    "DefaultKernelRegistry",
    "KernelError",
    "KernelHealthSnapshot",
    "KernelUnavailableError",
    "KernelUnsupportedOperationError",
    "ProbeResult",
    "WorkerCallError",
    "WorkerCrashedError",
    "WorkerError",
    "WorkerStartError",
    "WorkerTimeoutError",
    "create_default_registry",
]


def create_default_registry() -> DefaultKernelRegistry:
    """Build a registry with the built-in kernels registered (imported lazily)."""
    from atomcd.kernels.builtin import create_registry

    return create_registry()
