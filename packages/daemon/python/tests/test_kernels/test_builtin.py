"""Built-in registration and the zero-optional-package daemon contract."""

from __future__ import annotations

from atomcd.kernels.builtin import create_registry, register_builtin_kernels
from atomcd.kernels.registry import DefaultKernelRegistry


def test_create_registry_registers_all_builtins() -> None:
    registry = create_registry()
    assert registry.names() == ["atopile", "kiutils", "ocp", "renode"]


def test_register_builtin_kernels_is_idempotent() -> None:
    registry = DefaultKernelRegistry()
    register_builtin_kernels(registry)
    register_builtin_kernels(registry)
    assert registry.names() == ["atopile", "kiutils", "ocp", "renode"]


async def test_health_all_without_any_hardware_installed() -> None:
    """A daemon environment with no optional kernels must not crash on health."""
    registry = create_registry()
    health = await registry.health_all()
    assert set(health) == {"atopile", "kiutils", "ocp", "renode"}
    for snapshot in health.values():
        assert snapshot.status != "ready"
        assert snapshot.availability in {"unavailable", "error"}
    assert await registry.shutdown() is None
