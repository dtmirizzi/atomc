"""Kernel registry protocol owned by the daemon core.

WP-2.3 defines the *interface only*; WP-2.4 implements the warm kernel registry under
``atomcd/kernels/`` (atopile/faebryk, OCP, pyrenode3, kiutils, …). Nothing here imports a
hardware engine eagerly so importing ``atomcd`` stays cheap and side-effect free.

Design notes carried into WP-2.4:

* OCP is not thread-safe, so the registry must run CAD in a dedicated worker **process**.
* Heavy runtime kernel dependencies live in the bootstrap/daemon environment and are imported
  lazily on ``start``/``get``, never at daemon import time.
* ``reload`` must be safe to call concurrently with in-flight ``get`` results (returned handles
  stay valid until released).
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

KernelStatus = Literal["unknown", "starting", "ready", "error", "stopped"]


class KernelHealth(Protocol):
    """Health snapshot for a single kernel."""

    @property
    def name(self) -> str: ...

    @property
    def status(self) -> KernelStatus: ...

    @property
    def detail(self) -> str | None: ...


@runtime_checkable
class Kernel(Protocol):
    """A lazily started warm kernel (e.g. atopile, OCP, pyrenode3, kiutils)."""

    @property
    def name(self) -> str: ...

    async def start(self) -> None:
        """Bring the kernel up (idempotent). Import heavy deps here, not at module import."""

    async def stop(self) -> None:
        """Tear the kernel down and release resources (idempotent)."""

    async def health(self) -> KernelHealth:
        """Return the current health without forcing a start."""

    async def call(self, op: str, **kwargs: Any) -> Any:
        """Invoke an operation on the kernel. Engines define their own ``op`` namespace."""


class KernelRegistry(Protocol):
    """Registry that manages kernel lifecycles for the daemon.

    The daemon core only depends on this protocol; it never imports a concrete kernel.
    """

    def register(self, name: str, factory: KernelFactory) -> None:
        """Register a kernel factory under ``name`` (replaces an existing registration)."""

    def names(self) -> list[str]:
        """Return the registered kernel names."""

    def get(self, name: str) -> Kernel:
        """Return the (not necessarily started) kernel handle. Raises ``KeyError`` if absent."""

    async def health(self, name: str) -> KernelHealth:
        """Return the current health for ``name``."""

    async def reload(self, name: str) -> Kernel:
        """Stop (if running), drop and re-create the kernel, returning the new handle."""

    async def shutdown(self) -> None:
        """Stop every started kernel (best effort)."""


class KernelFactory(Protocol):
    """Callable that constructs a fresh :class:`Kernel` instance."""

    def __call__(self) -> Kernel: ...


__all__ = [
    "Kernel",
    "KernelFactory",
    "KernelHealth",
    "KernelRegistry",
    "KernelStatus",
]
