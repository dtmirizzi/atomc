"""Health snapshots for warm kernels.

``KernelHealthSnapshot`` structurally satisfies :class:`atomcd.kernel_protocol.KernelHealth`
(``name`` / ``status`` / ``detail``) while carrying the extra operational fields the daemon and
``atomcd doctor`` want: availability, version, cold/warm state, last error and restart count.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from atomcd.kernel_protocol import KernelStatus

Availability = Literal["available", "unavailable", "error"]


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """Result of a cheap, side-effect-free availability probe.

    Probes must never import the heavy engine: they use ``importlib.util.find_spec`` and
    ``importlib.metadata`` only, so asking for health never pays the import cost.
    """

    available: bool
    detail: str = ""
    version: str | None = None


@dataclass(frozen=True, slots=True)
class KernelHealthSnapshot:
    """Point-in-time health for one kernel."""

    name: str
    status: KernelStatus
    detail: str | None = None
    version: str | None = None
    warm: bool = False
    last_error: str | None = None
    restart_count: int = 0
    cold_starts: int = 0

    @property
    def available(self) -> bool:
        """True only once the kernel is warm and ready to serve calls."""
        return self.status == "ready"

    @property
    def availability(self) -> Availability:
        """Coarse tri-state used by the daemon/doctor: available | unavailable | error."""
        if self.status == "ready":
            return "available"
        if self.status == "error":
            return "error"
        return "unavailable"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "version": self.version,
            "warm": self.warm,
            "last_error": self.last_error,
            "restart_count": self.restart_count,
            "cold_starts": self.cold_starts,
            "availability": self.availability,
        }


__all__ = ["Availability", "KernelHealthSnapshot", "ProbeResult"]
