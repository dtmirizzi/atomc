"""Opt-in smoke test for hosts that actually have the optional kernels installed.

Normal CI never installs atopile/build123d/pyrenode3/kiutils, so this test is skipped unless
``ATOMC_KERNEL_SMOKE=1`` is set. It exercises the *public* start/version surface only and never
claims an emulator run proves USB HID or HIL behavior.
"""

from __future__ import annotations

import os

import pytest
from atomcd.kernels.builtin import create_registry

pytestmark = pytest.mark.skipif(
    not os.environ.get("ATOMC_KERNEL_SMOKE"),
    reason="opt-in: set ATOMC_KERNEL_SMOKE=1 on a host with the hardware kernels installed",
)


async def test_installed_kernels_start_and_report_version() -> None:
    registry = create_registry()
    started: list[str] = []
    try:
        for name in registry.names():
            health = await registry.health(name)
            if not health.available:
                continue
            kernel = await registry.ensure(name)
            started.append(name)
            if name in {"atopile", "ocp", "renode"}:
                result = await kernel.call("version")
                assert result
    finally:
        await registry.shutdown()
