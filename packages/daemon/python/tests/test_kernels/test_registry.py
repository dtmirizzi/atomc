"""Registry semantics: lazy instantiation, serialization, health, reload, shutdown."""

from __future__ import annotations

import asyncio

import pytest
from atomcd.kernel_protocol import Kernel
from atomcd.kernels.registry import DefaultKernelRegistry
from atomcd.kernels.testing import CountingKernel


def test_registry_satisfies_protocol() -> None:
    # KernelRegistry is not @runtime_checkable; verify the structural shape instead.
    registry = DefaultKernelRegistry()
    for method in ("register", "names", "get", "health", "reload", "shutdown"):
        assert callable(getattr(registry, method))


def test_register_get_and_names() -> None:
    registry = DefaultKernelRegistry()
    registry.register("counting", CountingKernel)
    assert registry.names() == ["counting"]
    kernel = registry.get("counting")
    assert isinstance(kernel, Kernel)
    assert registry.get("counting") is kernel  # cached handle


def test_get_unknown_raises_keyerror() -> None:
    registry = DefaultKernelRegistry()
    with pytest.raises(KeyError):
        registry.get("nope")


def test_factory_is_lazy_and_called_once() -> None:
    calls: list[int] = []

    def factory() -> CountingKernel:
        calls.append(1)
        return CountingKernel()

    registry = DefaultKernelRegistry()
    registry.register("counting", factory)
    assert calls == []
    first = registry.get("counting")
    second = registry.get("counting")
    assert first is second
    assert calls == [1]


async def test_ensure_serializes_concurrent_cold_start() -> None:
    kernel = CountingKernel()
    registry = DefaultKernelRegistry()
    registry.register("counting", lambda: kernel)
    results = await asyncio.gather(
        registry.ensure("counting"),
        registry.ensure("counting"),
        registry.ensure("counting"),
    )
    assert all(result is kernel for result in results)
    assert kernel.starts == 1
    assert kernel.status == "ready"


async def test_health_missing_package_is_unavailable_not_crash() -> None:
    registry = DefaultKernelRegistry()
    registry.register("counting", lambda: CountingKernel(available=False))
    health = await registry.health("counting")
    assert health.status == "stopped"
    assert health.availability == "unavailable"


async def test_health_unknown_raises_keyerror() -> None:
    registry = DefaultKernelRegistry()
    with pytest.raises(KeyError):
        await registry.health("nope")


async def test_health_reports_factory_failure_as_error() -> None:
    def bad_factory() -> CountingKernel:
        raise RuntimeError("cannot construct")

    registry = DefaultKernelRegistry()
    registry.register("counting", bad_factory)
    health = await registry.health("counting")
    assert health.status == "error"
    assert health.availability == "error"
    assert health.last_error is not None
    assert "cannot construct" in health.last_error


async def test_health_all_covers_every_registered_kernel() -> None:
    registry = DefaultKernelRegistry()
    registry.register("a", lambda: CountingKernel())
    registry.register("b", lambda: CountingKernel(available=False))
    health = await registry.health_all()
    assert set(health) == {"a", "b"}
    assert health["a"].availability == "unavailable"  # cold, not started
    assert health["b"].availability == "unavailable"


async def test_reload_stops_old_and_marks_restart() -> None:
    registry = DefaultKernelRegistry()
    registry.register("counting", CountingKernel)
    old = registry.get("counting")
    await old.start()
    new = await registry.reload("counting")
    assert new is not old
    assert old.stops == 1
    assert old.status == "stopped"
    assert new.restart_count == 1
    assert registry.get("counting") is new
    assert new.status != "ready"  # reload returns a fresh, cold handle


async def test_reload_unknown_raises_keyerror() -> None:
    registry = DefaultKernelRegistry()
    with pytest.raises(KeyError):
        await registry.reload("nope")


async def test_shutdown_stops_every_started_kernel() -> None:
    first = CountingKernel()
    second = CountingKernel()
    registry = DefaultKernelRegistry()
    registry.register("first", lambda: first)
    registry.register("second", lambda: second)
    await registry.ensure("first")
    await registry.ensure("second")
    await registry.shutdown()
    assert first.stops == 1
    assert second.stops == 1
    assert first.status == "stopped"
    assert second.status == "stopped"


def test_register_empty_name_rejected() -> None:
    registry = DefaultKernelRegistry()
    with pytest.raises(ValueError, match="kernel name"):
        registry.register("", CountingKernel)
