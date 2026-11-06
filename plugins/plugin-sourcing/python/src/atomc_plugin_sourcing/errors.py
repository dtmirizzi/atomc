"""Typed failures for sourcing adapters and tools.

Adapters distinguish *unavailable* (no trustworthy external data could be obtained) from
*malformed* (a response arrived but did not match the documented shape). Callers surface both;
neither ever becomes a partial offer list.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "NormalizationError",
    "SourcingError",
    "SourcingQueryError",
    "VendorResponseError",
    "VendorUnavailableError",
]


class SourcingError(RuntimeError):
    """Base class for expected sourcing failures."""


class VendorUnavailableError(SourcingError):
    """No live data: missing credentials, unreachable endpoint or rejected auth."""

    def __init__(self, message: str, evidence: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.evidence = list(evidence or [])


class VendorResponseError(SourcingError):
    """A live response was malformed or otherwise untrustworthy."""

    def __init__(self, message: str, evidence: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.evidence = list(evidence or [])


class NormalizationError(SourcingError):
    """A vendor offer could not be validated as a frozen IR ``Offer``."""


class SourcingQueryError(SourcingError):
    """A tool payload was invalid or referred to a missing BOM line."""
