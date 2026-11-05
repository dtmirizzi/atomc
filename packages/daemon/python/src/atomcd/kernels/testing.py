"""Deterministic fakes used by the kernel tests and by local smoke runs.

Like :mod:`atomcd.testing`, this module is importable by a ``spawn``-ed worker process so it can
resolve the ``atomcd.kernels.testing:make_fake_engine`` factory by dotted path. It never imports a
hardware engine.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from atomcd.kernels.base import BaseKernel
from atomcd.kernels.health import ProbeResult


class CountingKernel(BaseKernel):
    """Deterministic kernel used to exercise lifecycle transitions."""

    def __init__(self, *, available: bool = True, fail_start: bool = False) -> None:
        super().__init__("counting", package="counting")
        self.starts = 0
        self.stops = 0
        self.calls: list[str] = []
        self._available = available
        self._fail_start = fail_start

    def _probe(self) -> ProbeResult:
        if not self._available:
            return ProbeResult(available=False, detail="missing: counting", version=None)
        return ProbeResult(available=True, detail="installed", version="1.0.0")

    async def _start(self) -> None:
        self.starts += 1
        await asyncio.sleep(0.02)
        if self._fail_start:
            raise RuntimeError("synthetic start failure")

    async def _stop(self) -> None:
        self.stops += 1

    async def _call(self, op: str, **kwargs: Any) -> Any:
        self.calls.append(op)
        return {"op": op, "kwargs": kwargs}


class FakeWorkerEngine:
    """In-memory engine exercising the worker protocol edges."""

    def __init__(self) -> None:
        self.closed = False
        self.calls: list[str] = []

    def handle(self, op: str, kwargs: dict[str, Any]) -> Any:
        self.calls.append(op)
        if op == "ping":
            return {"pong": True, "pid": os.getpid()}
        if op == "version":
            return {"fake": "1.0.0", "pid": os.getpid()}
        if op == "echo":
            return {"op": op, "kwargs": kwargs}
        if op == "sleep":
            seconds = float(kwargs.get("seconds", 0.0))
            time.sleep(seconds)
            return {"slept": seconds}
        if op == "boom":
            raise RuntimeError("boom")
        if op == "crash":
            os._exit(3)
        raise ValueError(f"unknown fake op {op!r}")

    def close(self) -> None:
        self.closed = True


class FakeCrashingEngine(FakeWorkerEngine):
    """Fake engine whose ``ping`` hard-crashes, to exercise OCP worker recovery."""

    def handle(self, op: str, kwargs: dict[str, Any]) -> Any:
        if op == "ping":
            os._exit(7)
        return super().handle(op, kwargs)


def make_fake_engine() -> FakeWorkerEngine:
    """Zero-argument engine factory resolved inside the worker process."""
    return FakeWorkerEngine()


def make_crashing_engine() -> FakeCrashingEngine:
    """Factory for the crash-on-ping engine."""
    return FakeCrashingEngine()


__all__ = [
    "CountingKernel",
    "FakeCrashingEngine",
    "FakeWorkerEngine",
    "make_crashing_engine",
    "make_fake_engine",
]
