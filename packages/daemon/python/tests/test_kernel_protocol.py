"""Kernel registry protocol boundary (WP-2.4) and logging setup import smoke."""

from __future__ import annotations

from typing import Any

from atomcd.kernel_protocol import Kernel, KernelFactory, KernelHealth, KernelRegistry
from atomcd.logging import configure_logging, get_logger


class FakeHealth:
    def __init__(self, name: str, status: str = "ready") -> None:
        self._name = name
        self._status = status

    @property
    def name(self) -> str:
        return self._name

    @property
    def status(self) -> str:
        return self._status

    @property
    def detail(self) -> str | None:
        return None


class FakeKernel:
    def __init__(self, name: str = "fake") -> None:
        self._name = name
        self.started = False
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False

    async def health(self) -> Any:
        return FakeHealth(self._name)

    async def call(self, op: str, **kwargs: Any) -> Any:
        self.calls.append(op)
        return {"op": op, "kwargs": kwargs}


def test_fake_kernel_satisfies_protocol() -> None:
    assert isinstance(FakeKernel(), Kernel)


async def test_kernel_lifecycle() -> None:
    kernel = FakeKernel()
    assert isinstance(await kernel.health(), KernelHealth)
    await kernel.start()
    assert kernel.started is True
    assert await kernel.call("op", x=1) == {"op": "op", "kwargs": {"x": 1}}
    await kernel.stop()
    assert kernel.started is False


def test_registry_protocol_is_manifest_only() -> None:
    # The protocols are structural: a minimal factory callable is enough to type-check.
    def factory() -> Kernel:
        return FakeKernel()

    assert KernelFactory is not None
    assert KernelRegistry is not None


def test_logging_configure_and_get() -> None:
    configure_logging("debug")
    logger = get_logger("test")
    logger.info("hello", token="should-not-appear-in-structured-fields")
