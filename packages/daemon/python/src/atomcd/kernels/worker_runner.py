"""Child-process entrypoint for supervised kernel workers.

This module is the target of a ``spawn``-ed :class:`multiprocessing.Process`. It intentionally
does not import any hardware engine at module scope: the engine factory is resolved lazily from a
dotted path and constructed inside the child, so the parent daemon never pays the import cost and
never forks a multithreaded process.

Protocol (JSON-compatible messages over a duplex pipe):

* child → parent: ``{"event": "ready"}`` once the engine is constructed, or
  ``{"event": "startup_error", "error": {...}}`` if construction fails;
* parent → child: ``{"id": <int>, "op": <str>, "kwargs": {...}}`` or ``None`` to shut down;
* child → parent: ``{"id": <int>, "ok": true, "result": ...}`` or
  ``{"id": <int>, "ok": false, "error": {"type": ..., "message": ...}}``.

Geometry never travels over the pipe: OCP operations return STEP artifact paths, keeping the IPC
bounded and JSON-serialisable.
"""

from __future__ import annotations

import contextlib
import importlib
import os
import socket
import traceback
from typing import Any, Protocol


class WorkerEngine(Protocol):
    """Duck-typed engine constructed inside the worker process."""

    def handle(self, op: str, kwargs: dict[str, Any]) -> Any: ...

    def close(self) -> None: ...


def load_factory(path: str) -> Any:
    """Resolve ``"module:attr"`` to a zero-argument engine factory."""
    module_name, sep, attr = path.partition(":")
    if not sep or not module_name or not attr:
        raise ValueError(f"invalid factory path {path!r}; expected 'module:attr'")
    module = importlib.import_module(module_name)
    return getattr(module, attr)


def worker_main(conn: Any, factory_path: str) -> None:
    """Run the worker loop until the pipe closes or ``None`` is received."""
    engine: WorkerEngine | None = None
    try:
        try:
            factory = load_factory(factory_path)
            engine = factory()
        except BaseException as exc:
            conn.send(
                {
                    "event": "startup_error",
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                }
            )
            return
        conn.send({"event": "ready", "pid": os.getpid()})
        _loop(conn, engine)
    except EOFError:
        pass
    finally:
        if engine is not None:
            with contextlib.suppress(Exception):
                engine.close()
        with contextlib.suppress(Exception):
            conn.close()


def _loop(conn: Any, engine: WorkerEngine) -> None:
    while True:
        message = conn.recv()
        if message is None:
            return
        req_id = message.get("id")
        op = message.get("op", "")
        kwargs = message.get("kwargs") or {}
        try:
            result = engine.handle(op, kwargs)
        except BaseException as exc:
            conn.send(
                {
                    "id": req_id,
                    "ok": False,
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                }
            )
        else:
            conn.send({"id": req_id, "ok": True, "result": result})


def describe_host() -> dict[str, Any]:
    """Small diagnostic payload used by worker engines."""
    return {
        "pid": os.getpid(),
        "host": socket.gethostname(),
    }


def format_exception(exc: BaseException) -> str:
    return "".join(traceback.format_exception_only(type(exc), exc)).strip()


__all__ = ["WorkerEngine", "describe_host", "format_exception", "load_factory", "worker_main"]
