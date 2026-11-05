"""build123d/OCP kernel backed by a supervised worker process.

OCP is not thread-safe and must never be forked out of the multithreaded daemon, so all geometry
work runs in a ``spawn``-ed child behind :class:`atomcd.kernels.process.WorkerProcess`. Requests
are serialized, the child is restarted on crash/timeout, and the kernel reports the worker's
restart count.
"""

from __future__ import annotations

import asyncio
from typing import Any

from atomcd.kernels.base import BaseKernel
from atomcd.kernels.errors import KernelUnsupportedOperationError, WorkerError
from atomcd.kernels.health import ProbeResult
from atomcd.kernels.importer import probe_modules
from atomcd.kernels.process import WorkerProcess

WORKER_FACTORY = "atomcd.kernels.ocp_engine:make_engine"


class OcpKernel(BaseKernel):
    """Serialize CAD work into one restartable worker process."""

    def __init__(
        self,
        *,
        worker_factory_path: str = WORKER_FACTORY,
        job_timeout_s: float = 120.0,
        start_timeout_s: float = 60.0,
        max_restarts: int = 3,
    ) -> None:
        super().__init__("ocp", package="build123d")
        self._worker_factory_path = worker_factory_path
        self._job_timeout_s = job_timeout_s
        self._start_timeout_s = start_timeout_s
        self._max_restarts = max_restarts
        self._worker: WorkerProcess | None = None

    @property
    def worker(self) -> WorkerProcess | None:
        return self._worker

    def _probe(self) -> ProbeResult:
        return probe_modules("build123d", "OCP", distribution="build123d")

    async def _start(self) -> None:
        worker = WorkerProcess(
            self._worker_factory_path,
            name="ocp",
            job_timeout_s=self._job_timeout_s,
            start_timeout_s=self._start_timeout_s,
            max_restarts=self._max_restarts,
        )
        # start() is blocking (spawn + handshake); keep the event loop responsive.
        await asyncio.to_thread(worker.start)
        try:
            await asyncio.to_thread(worker.request, "version", {}, timeout=self._start_timeout_s)
        except WorkerError:
            worker.close()
            raise
        self._worker = worker

    async def _stop(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            await asyncio.to_thread(worker.close)

    async def _call(self, op: str, **kwargs: Any) -> Any:
        if op not in ("ping", "version", "make_box", "export_step"):
            raise KernelUnsupportedOperationError(
                self.name,
                op,
                "supported ops: ping, version, make_box, export_step",
            )
        worker = self._worker
        if worker is None:  # pragma: no cover - call() guarantees _start
            raise WorkerError("ocp worker is not running")
        try:
            return await asyncio.to_thread(worker.request, op, kwargs)
        except WorkerError:
            # Worker crashes/restarts are counted toward kernel health.
            self.mark_restart()
            raise
        finally:
            self._sync_worker_stats(worker)

    def _sync_worker_stats(self, worker: WorkerProcess) -> None:
        self._restart_count = max(self._restart_count, worker.restart_count)


__all__ = ["WORKER_FACTORY", "OcpKernel"]
