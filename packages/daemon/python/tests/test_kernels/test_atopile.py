"""Atopile adapter: version/availability only, explicit unsupported build."""

from __future__ import annotations

import sys
import types

import pytest
from atomcd.kernels.atopile import AtopileKernel
from atomcd.kernels.errors import KernelUnsupportedOperationError
from atomcd.kernels.health import ProbeResult


async def test_health_unavailable_without_atopile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "atomcd.kernels.atopile.probe_modules",
        lambda *args, **kwargs: ProbeResult(available=False, detail="missing: atopile"),
    )
    health = await AtopileKernel().health()
    assert health.availability == "unavailable"


async def test_version_and_unsupported_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "atopile", types.ModuleType("atopile"))
    kernel = AtopileKernel()
    kernel._probe = lambda: ProbeResult(available=True, detail="installed", version="0.15.9")  # type: ignore[method-assign]
    await kernel.start()
    try:
        version = await kernel.call("version")
        assert version["atopile"] == "0.15.9"
        assert await kernel.call("ping") == {"pong": True}
        with pytest.raises(KernelUnsupportedOperationError):
            await kernel.call("build")
    finally:
        await kernel.stop()
