"""Common lifecycle machinery for warm kernels.

Each concrete adapter subclasses :class:`BaseKernel` and implements four hooks:

* ``_probe``  — cheap availability/version check (never imports the engine);
* ``_start``  — import heavy dependencies and bring the engine up;
* ``_stop``   — release engine resources;
* ``_call``   — dispatch an operation after the kernel is warm.

Lifecycle transitions are guarded by a per-kernel :class:`asyncio.Lock`, so concurrent
``start`` calls perform exactly one cold start and concurrent ``call``s cannot race a reload.
"""

from __future__ import annotations

import asyncio
from typing import Any

from atomcd.kernel_protocol import KernelStatus
from atomcd.kernels.errors import KernelUnavailableError
from atomcd.kernels.health import KernelHealthSnapshot, ProbeResult
from atomcd.logging import get_logger

_LOGGER_NAME = "atomcd.kernels"


class BaseKernel:
    """Shared, dependency-free implementation of the :class:`Kernel` protocol."""

    def __init__(self, name: str, *, package: str | None = None) -> None:
        self._name = name
        self._package = package
        self._status: KernelStatus = "unknown"
        self._detail: str | None = None
        self._version: str | None = None
        self._last_error: str | None = None
        self._restart_count = 0
        self._cold_starts = 0
        self._started = False
        self._lifecycle = asyncio.Lock()
        self._logger = get_logger(_LOGGER_NAME)

    # -- Kernel protocol ------------------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    @property
    def status(self) -> KernelStatus:
        return self._status

    @property
    def detail(self) -> str | None:
        return self._detail

    async def start(self) -> None:
        """Bring the kernel up exactly once; idempotent."""
        async with self._lifecycle:
            if self._status == "ready" and self._started:
                return
            probe = self._probe()
            self._version = probe.version or self._version
            if not probe.available:
                self._status = "stopped"
                self._detail = f"unavailable: {probe.detail}"
                raise KernelUnavailableError(self._name, probe.detail)
            self._status = "starting"
            self._detail = None
            self._logger.info("kernel.start", kernel=self._name)
            try:
                await self._start()
            except KernelUnavailableError as exc:
                self._status = "stopped"
                self._detail = f"unavailable: {exc.detail}"
                raise
            except Exception as exc:
                self._status = "error"
                self._last_error = f"{type(exc).__name__}: {exc}"
                self._logger.error("kernel.start_failed", kernel=self._name, error=self._last_error)
                raise
            self._started = True
            self._cold_starts += 1
            self._status = "ready"
            self._detail = "warm"
            self._logger.info("kernel.ready", kernel=self._name, version=self._version)

    async def stop(self) -> None:
        """Tear the kernel down; idempotent and safe to call while never started."""
        async with self._lifecycle:
            if not self._started:
                if self._status in ("unknown", "starting"):
                    self._status = "stopped"
                if self._status != "error":
                    self._detail = "stopped"
                return
            self._logger.info("kernel.stop", kernel=self._name)
            try:
                await self._stop()
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
                self._logger.warning(
                    "kernel.stop_failed", kernel=self._name, error=self._last_error
                )
            finally:
                self._started = False
                self._status = "stopped"
                self._detail = "stopped"

    async def health(self) -> KernelHealthSnapshot:
        """Return health without forcing a start."""
        if self._status == "ready":
            return self._snapshot(status="ready", warm=True, detail="warm")
        if self._status in ("starting", "error"):
            return self._snapshot(status=self._status, warm=False)
        probe = self._probe()
        if not probe.available:
            return self._snapshot(
                status="stopped",
                warm=False,
                detail=f"unavailable: {probe.detail}",
                version=probe.version,
            )
        return self._snapshot(
            status="stopped",
            warm=False,
            detail="cold",
            version=probe.version,
        )

    async def call(self, op: str, **kwargs: Any) -> Any:
        """Start the kernel if needed, then dispatch ``op``."""
        await self.start()
        return await self._call(op, **kwargs)

    # -- extension points -----------------------------------------------------

    def _probe(self) -> ProbeResult:
        """Cheap availability probe. Default: available."""
        return ProbeResult(available=True, detail="installed", version=self._version)

    async def _start(self) -> None:
        """Bring the engine up. Import heavy dependencies here only."""

    async def _stop(self) -> None:
        """Release engine resources."""

    async def _call(self, op: str, **kwargs: Any) -> Any:
        raise NotImplementedError(f"{self._name} does not implement op {op!r}")

    # -- helpers for the registry --------------------------------------------

    def mark_restart(self) -> None:
        """Record that the registry replaced/restarted this kernel."""
        self._restart_count += 1

    @property
    def restart_count(self) -> int:
        return self._restart_count

    def _snapshot(
        self,
        *,
        status: KernelStatus,
        warm: bool,
        detail: str | None = None,
        version: str | None = None,
    ) -> KernelHealthSnapshot:
        return KernelHealthSnapshot(
            name=self._name,
            status=status,
            detail=detail if detail is not None else self._detail,
            version=version if version is not None else self._version,
            warm=warm,
            last_error=self._last_error,
            restart_count=self._restart_count,
            cold_starts=self._cold_starts,
        )


__all__ = ["BaseKernel"]
