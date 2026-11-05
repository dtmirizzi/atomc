"""Supervised worker-process manager for engines that are not thread-safe (OCP/build123d).

OCP holds a global C++ state that is not safe to call from multiple threads, and forking a
multithreaded daemon is undefined behaviour. This manager therefore uses an explicit ``spawn``
context, runs exactly one job at a time (a :class:`threading.Lock` serialises requests), and
recovers from crashes/timeouts by terminating and respawning the worker.

The request/response payloads are JSON-compatible. Geometry is passed by artifact path (STEP),
never inline, so the pipe stays bounded.
"""

from __future__ import annotations

import contextlib
import itertools
import multiprocessing
import threading
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from typing import Any

from atomcd.kernels.errors import (
    WorkerCallError,
    WorkerCrashedError,
    WorkerStartError,
    WorkerTimeoutError,
)
from atomcd.kernels.worker_runner import worker_main
from atomcd.logging import get_logger

START_METHOD = "spawn"
DEFAULT_JOB_TIMEOUT_S = 120.0
DEFAULT_START_TIMEOUT_S = 60.0
DEFAULT_SHUTDOWN_TIMEOUT_S = 5.0
DEFAULT_MAX_RESTARTS = 3


class WorkerProcess:
    """One supervised worker process behind a serialized request API."""

    def __init__(
        self,
        factory_path: str,
        *,
        name: str = "worker",
        job_timeout_s: float = DEFAULT_JOB_TIMEOUT_S,
        start_timeout_s: float = DEFAULT_START_TIMEOUT_S,
        shutdown_timeout_s: float = DEFAULT_SHUTDOWN_TIMEOUT_S,
        max_restarts: int = DEFAULT_MAX_RESTARTS,
        start_method: str = START_METHOD,
    ) -> None:
        self._factory_path = factory_path
        self._name = name
        self._job_timeout_s = job_timeout_s
        self._start_timeout_s = start_timeout_s
        self._shutdown_timeout_s = shutdown_timeout_s
        self._max_restarts = max_restarts
        # ``BaseContext`` in typeshed omits ``Process``/``Pipe``; they exist on every concrete
        # context. Typed as Any to keep the explicit spawn context without a cast at each use.
        self._ctx: Any = multiprocessing.get_context(start_method)
        self._process: BaseProcess | None = None
        self._conn: Connection | None = None
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._start_count = 0
        self._restart_count = 0
        self._last_error: str | None = None
        self._closed = False
        self._logger = get_logger("atomcd.kernels.worker")

    # -- introspection --------------------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    @property
    def pid(self) -> int | None:
        process = self._process
        return process.pid if process is not None else None

    @property
    def alive(self) -> bool:
        process = self._process
        return bool(process is not None and process.is_alive())

    @property
    def start_count(self) -> int:
        return self._start_count

    @property
    def restart_count(self) -> int:
        return self._restart_count

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def closed(self) -> bool:
        return self._closed

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> None:
        """Spawn the worker if it is not already running."""
        with self._lock:
            if self._closed:
                raise WorkerStartError(f"{self._name} worker is closed")
            if self.alive:
                return
            self._spawn()

    def request(
        self,
        op: str,
        kwargs: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        """Send one request and return its result, serialized against other callers."""
        with self._lock:
            if self._closed:
                raise WorkerCrashedError(f"{self._name} worker is closed")
            self._ensure_alive()
            conn = self._conn
            if conn is None:  # pragma: no cover - _ensure_alive guarantees a connection
                raise WorkerStartError(f"{self._name} worker has no connection")
            req_id = next(self._ids)
            deadline = self._job_timeout_s if timeout is None else timeout
            try:
                conn.send({"id": req_id, "op": op, "kwargs": kwargs or {}})
            except (BrokenPipeError, OSError) as exc:
                self._record_crash(f"send failed on op {op!r}: {exc}")
                raise WorkerCrashedError(f"{self._name} crashed during {op!r}") from exc
            if not conn.poll(deadline):
                self._record_crash(f"timeout after {deadline}s on op {op!r}")
                raise WorkerTimeoutError(f"{self._name} timed out after {deadline}s on {op!r}")
            try:
                message = conn.recv()
            except EOFError as exc:
                self._record_crash(f"worker exited during op {op!r}")
                raise WorkerCrashedError(f"{self._name} exited during {op!r}") from exc
            if message.get("id") != req_id:
                self._hard_terminate()
                self._last_error = f"protocol mismatch: expected id {req_id}"
                raise WorkerCrashedError(self._last_error)
            if not message.get("ok"):
                error = message.get("error") or {}
                raise WorkerCallError(
                    op, str(error.get("type", "error")), str(error.get("message", ""))
                )
            return message.get("result")

    def close(self) -> None:
        """Ask the worker to exit, then hard-terminate if it will not."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            conn = self._conn
            process = self._process
            if conn is not None and process is not None and process.is_alive():
                with contextlib.suppress(BrokenPipeError, OSError):
                    conn.send(None)
                process.join(self._shutdown_timeout_s)
            self._hard_terminate()
            self._logger.info("worker.closed", worker=self._name, starts=self._start_count)

    def terminate(self) -> None:
        """Terminate immediately without a graceful shutdown message."""
        with self._lock:
            self._hard_terminate()

    # -- internals ------------------------------------------------------------

    def _spawn(self) -> None:
        parent_conn, child_conn = self._ctx.Pipe(duplex=True)
        process = self._ctx.Process(
            target=worker_main,
            args=(child_conn, self._factory_path),
            daemon=True,
            name=f"atomcd-{self._name}",
        )
        process.start()
        child_conn.close()
        self._process = process
        self._conn = parent_conn
        self._start_count += 1
        try:
            if not parent_conn.poll(self._start_timeout_s):
                raise WorkerStartError(
                    f"{self._name} worker did not report ready within {self._start_timeout_s}s"
                )
            message = parent_conn.recv()
        except EOFError as exc:
            self._hard_terminate()
            raise WorkerStartError(f"{self._name} worker exited during startup") from exc
        except WorkerStartError:
            self._hard_terminate()
            raise
        if message.get("event") == "startup_error":
            error = message.get("error") or {}
            self._hard_terminate()
            raise WorkerStartError(
                f"{self._name} engine failed to start: "
                f"{error.get('type', 'error')}: {error.get('message', '')}"
            )
        if message.get("event") != "ready":
            self._hard_terminate()
            raise WorkerStartError(f"{self._name} worker sent unexpected startup message")
        self._logger.debug("worker.ready", worker=self._name, pid=process.pid)

    def _ensure_alive(self) -> None:
        process = self._process
        if process is not None and process.is_alive() and self._conn is not None:
            return
        if process is not None:
            # It died between requests: account for a restart before respawning.
            self._hard_terminate()
            self._restart_count += 1
        if self._restart_count > self._max_restarts:
            raise WorkerStartError(f"{self._name} exceeded max restarts ({self._max_restarts})")
        self._spawn()

    def _record_crash(self, reason: str) -> None:
        self._last_error = reason
        self._logger.error("worker.crash", worker=self._name, reason=reason)
        self._hard_terminate()
        self._restart_count += 1

    def _hard_terminate(self) -> None:
        process = self._process
        if process is not None:
            with contextlib.suppress(ValueError):
                if process.is_alive():
                    process.terminate()
                    process.join(self._shutdown_timeout_s)
                if process.is_alive():  # pragma: no cover - kill is a last resort
                    process.kill()
                    process.join(self._shutdown_timeout_s)
            with contextlib.suppress(ValueError, OSError):
                process.close()
        self._process = None
        conn = self._conn
        if conn is not None:
            with contextlib.suppress(OSError):
                conn.close()
        self._conn = None


__all__ = ["DEFAULT_JOB_TIMEOUT_S", "START_METHOD", "WorkerProcess"]
