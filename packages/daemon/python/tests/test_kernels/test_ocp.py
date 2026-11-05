"""OCP kernel: worker isolation, op routing, missing-toolchain health."""

from __future__ import annotations

import pytest
from atomcd.kernels.errors import KernelUnsupportedOperationError, WorkerCrashedError
from atomcd.kernels.health import ProbeResult
from atomcd.kernels.ocp import OcpKernel

FAKE = "atomcd.kernels.testing:make_fake_engine"
CRASHING = "atomcd.kernels.testing:make_crashing_engine"


def _available(kernel: OcpKernel) -> None:
    kernel._probe = lambda: ProbeResult(available=True, detail="test", version="0")  # type: ignore[method-assign]


async def test_health_unavailable_without_toolchain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "atomcd.kernels.ocp.probe_modules",
        lambda *args, **kwargs: ProbeResult(available=False, detail="missing: build123d, OCP"),
    )
    kernel = OcpKernel()
    health = await kernel.health()
    assert health.status == "stopped"
    assert health.availability == "unavailable"
    assert kernel.worker is None


async def test_fake_worker_lifecycle_and_ops(monkeypatch: pytest.MonkeyPatch) -> None:
    kernel = OcpKernel(worker_factory_path=FAKE, job_timeout_s=5.0, start_timeout_s=15.0)
    _available(kernel)
    await kernel.start()
    try:
        assert kernel.worker is not None
        assert (await kernel.call("ping"))["pong"] is True
        assert (await kernel.call("version"))["fake"] == "1.0.0"
        with pytest.raises(KernelUnsupportedOperationError):
            await kernel.call("nonsense")
    finally:
        await kernel.stop()
    assert kernel.status == "stopped"
    assert kernel.worker is None


async def test_worker_crash_bumps_restart_count(monkeypatch: pytest.MonkeyPatch) -> None:
    kernel = OcpKernel(worker_factory_path=CRASHING, job_timeout_s=5.0, start_timeout_s=15.0)
    _available(kernel)
    await kernel.start()
    try:
        with pytest.raises(WorkerCrashedError):
            await kernel.call("ping")
        assert kernel.restart_count >= 1
    finally:
        await kernel.stop()
