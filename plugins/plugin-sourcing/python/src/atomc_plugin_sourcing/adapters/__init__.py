"""Built-in sourcing adapters and their default construction."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime

import httpx

from .base import VendorAdapter
from .digikey import DigiKeyAdapter
from .lcsc import LcscAdapter
from .mouser import MouserAdapter
from .nexar import NexarAdapter

__all__ = ["DEFAULT_VENDORS", "build_adapters"]

DEFAULT_VENDORS: tuple[str, ...] = ("lcsc", "mouser", "digikey", "nexar")


def build_adapters(
    *,
    env: Mapping[str, str] | None = None,
    transport: httpx.BaseTransport | None = None,
    clock: Callable[[], datetime] | None = None,
    timeout_s: float = 15.0,
) -> dict[str, VendorAdapter]:
    """Construct one adapter per supported vendor.

    A shared ``transport`` is mainly useful in tests (replay cassettes); production callers
    omit it and each adapter creates a normal ``httpx.Client`` for its request.
    """
    kwargs = {
        "env": env,
        "transport": transport,
        "clock": clock,
        "timeout_s": timeout_s,
    }
    return {
        "lcsc": LcscAdapter(**kwargs),
        "mouser": MouserAdapter(**kwargs),
        "digikey": DigiKeyAdapter(**kwargs),
        "nexar": NexarAdapter(**kwargs),
    }
