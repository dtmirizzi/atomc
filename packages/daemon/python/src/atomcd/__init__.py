"""``atomcd`` — the atomc daemon.

Owns the system IR, the reactive DAG scheduler, the gate runner, plugin discovery and the
authenticated JSON-RPC host. Heavy hardware engines are *not* imported here; see
:mod:`atomcd.kernel_protocol` for the boundary implemented by WP-2.4.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:  # pragma: no cover - depends on install mode
    VERSION = version("atomc-daemon")
except PackageNotFoundError:  # pragma: no cover - source checkout
    VERSION = "0.0.1"

__all__ = ["VERSION"]
