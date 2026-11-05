"""Default warm-kernel registry.

Implements the :class:`atomcd.kernel_protocol.KernelRegistry` protocol: lazy instantiation by
name, one serialized cold start per kernel, health without forcing a start, reload and async
shutdown. It never imports a concrete engine itself — callers register factories and the daemon
decides which ones to wire in.
"""

from __future__ import annotations

import asyncio
from typing import cast

from atomcd.kernel_protocol import Kernel, KernelFactory
from atomcd.kernels.health import KernelHealthSnapshot
from atomcd.logging import get_logger

_LOGGER_NAME = "atomcd.kernels"


class DefaultKernelRegistry:
    """Concrete :class:`KernelRegistry` with per-kernel lifecycle locks."""

    def __init__(self) -> None:
        self._factories: dict[str, KernelFactory] = {}
        self._kernels: dict[str, Kernel] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._closed = False
        self._logger = get_logger(_LOGGER_NAME)

    # -- registration ---------------------------------------------------------

    def register(self, name: str, factory: KernelFactory) -> None:
        """Register (or replace) the factory for ``name``.

        Replacing a running kernel drops the old handle; call :meth:`reload` first when you
        need a graceful stop of the previous engine.
        """
        if not name:
            raise ValueError("kernel name must be non-empty")
        self._factories[name] = factory
        self._kernels.pop(name, None)
        self._locks.setdefault(name, asyncio.Lock())
        self._closed = False

    def names(self) -> list[str]:
        return sorted(self._factories)

    def registered(self, name: str) -> bool:
        return name in self._factories

    # -- lifecycle ------------------------------------------------------------

    def get(self, name: str) -> Kernel:
        """Return the kernel handle, instantiating it lazily on first access."""
        if name not in self._factories:
            raise KeyError(name)
        kernel = self._kernels.get(name)
        if kernel is None:
            kernel = self._factories[name]()
            self._kernels[name] = kernel
            self._logger.debug("kernel.instantiated", kernel=name)
        return kernel

    async def ensure(self, name: str) -> Kernel:
        """Return a started kernel, serializing concurrent cold starts."""
        async with self._lock_for(name):
            kernel = self.get(name)
            await kernel.start()
            return kernel

    async def health(self, name: str) -> KernelHealthSnapshot:
        """Return health for ``name`` without starting it."""
        if name not in self._factories:
            raise KeyError(name)
        try:
            kernel = self.get(name)
        except Exception as exc:
            self._logger.error("kernel.factory_failed", kernel=name, error=str(exc))
            return KernelHealthSnapshot(
                name=name,
                status="error",
                detail=f"factory failed: {type(exc).__name__}: {exc}",
                last_error=f"{type(exc).__name__}: {exc}",
            )
        return cast(KernelHealthSnapshot, await kernel.health())

    async def health_all(self) -> dict[str, KernelHealthSnapshot]:
        """Health for every registered kernel, keyed by name."""
        return {name: await self.health(name) for name in self.names()}

    async def reload(self, name: str) -> Kernel:
        """Stop the current kernel (if any) and return a fresh, not-yet-started handle."""
        if name not in self._factories:
            raise KeyError(name)
        async with self._lock_for(name):
            old = self._kernels.pop(name, None)
            if old is not None:
                try:
                    await old.stop()
                except Exception as exc:
                    self._logger.warning("kernel.reload_stop_failed", kernel=name, error=str(exc))
            kernel = self._factories[name]()
            _mark_restart(kernel)
            self._kernels[name] = kernel
            self._logger.info("kernel.reloaded", kernel=name)
            return kernel

    async def shutdown(self) -> None:
        """Stop every instantiated kernel, best effort."""
        self._closed = True
        kernels = list(self._kernels.values())
        self._kernels.clear()
        results = await asyncio.gather(*(k.stop() for k in kernels), return_exceptions=True)
        for kernel, result in zip(kernels, results, strict=True):
            if isinstance(result, BaseException):
                self._logger.warning(
                    "kernel.shutdown_failed",
                    kernel=kernel.name,
                    error=f"{type(result).__name__}: {result}",
                )
        self._logger.info("kernel.shutdown", kernels=len(kernels))

    # -- internals ------------------------------------------------------------

    def _lock_for(self, name: str) -> asyncio.Lock:
        lock = self._locks.get(name)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[name] = lock
        return lock


def _mark_restart(kernel: Kernel) -> None:
    mark = getattr(kernel, "mark_restart", None)
    if callable(mark):
        mark()


__all__ = ["DefaultKernelRegistry"]
