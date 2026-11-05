"""Lifecycle semantics of :class:`atomcd.kernels.base.BaseKernel`."""

from __future__ import annotations

import asyncio

import pytest
from atomcd.kernel_protocol import Kernel, KernelHealth
from atomcd.kernels.errors import KernelUnavailableError
from atomcd.kernels.testing import CountingKernel


def test_counting_kernel_satisfies_protocol() -> None:
    assert isinstance(CountingKernel(), Kernel)


async def test_start_is_idempotent_and_serialized() -> None:
    kernel = CountingKernel()
    await asyncio.gather(kernel.start(), kernel.start(), kernel.start())
    assert kernel.starts == 1
    assert kernel.status == "ready"
    assert kernel.detail == "warm"


async def test_health_reports_unavailable_without_start() -> None:
    kernel = CountingKernel(available=False)
    health = await kernel.health()
    assert isinstance(health, KernelHealth)
    assert health.status == "stopped"
    assert health.availability == "unavailable"
    assert health.available is False
    assert health.detail is not None
    assert "missing: counting" in health.detail
    assert kernel.starts == 0


async def test_call_auto_starts_and_dispatches() -> None:
    kernel = CountingKernel()
    result = await kernel.call("do", x=1)
    assert result == {"op": "do", "kwargs": {"x": 1}}
    assert kernel.calls == ["do"]
    assert kernel.status == "ready"


async def test_unavailable_start_raises_and_stays_cold() -> None:
    kernel = CountingKernel(available=False)
    with pytest.raises(KernelUnavailableError):
        await kernel.start()
    assert kernel.starts == 0
    assert kernel.status == "stopped"
    health = await kernel.health()
    assert health.availability == "unavailable"


async def test_error_during_start_marks_error_state() -> None:
    kernel = CountingKernel(fail_start=True)
    with pytest.raises(RuntimeError):
        await kernel.start()
    assert kernel.status == "error"
    health = await kernel.health()
    assert health.status == "error"
    assert health.availability == "error"
    assert health.last_error is not None
    assert "synthetic start failure" in health.last_error


async def test_stop_before_start_is_safe() -> None:
    kernel = CountingKernel()
    await kernel.stop()
    assert kernel.status == "stopped"
    assert kernel.stops == 0


async def test_stop_is_idempotent() -> None:
    kernel = CountingKernel()
    await kernel.start()
    await kernel.stop()
    await kernel.stop()
    assert kernel.stops == 1
    assert kernel.status == "stopped"


async def test_health_reports_warm_metadata() -> None:
    kernel = CountingKernel()
    await kernel.start()
    health = await kernel.health()
    assert health.warm is True
    assert health.availability == "available"
    assert health.version == "1.0.0"
    assert health.cold_starts == 1


async def test_mark_restart_is_reported() -> None:
    kernel = CountingKernel()
    kernel.mark_restart()
    kernel.mark_restart()
    health = await kernel.health()
    assert health.restart_count == 2
