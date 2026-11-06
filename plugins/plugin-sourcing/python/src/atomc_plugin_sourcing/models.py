"""Vendor-neutral sourcing models shared by adapters and the plugin service.

Nothing here invents inventory or prices: values only ever come from a parsed vendor response
(or a cache entry derived from one). The frozen IR ``Offer`` model is produced separately by
:mod:`atomc_plugin_sourcing.normalize`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

__all__ = [
    "AdapterResult",
    "ComponentQuery",
    "OfferPrice",
    "VendorOffer",
    "format_timestamp",
    "utcnow",
]

AdapterStatus = Literal["OK", "UNAVAILABLE", "ERROR"]


def utcnow() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(UTC)


def format_timestamp(value: datetime) -> str:
    """Serialise a timestamp as RFC 3339 UTC (``YYYY-MM-DDTHH:MM:SSZ``)."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True, slots=True)
class ComponentQuery:
    """What to ask a vendor about. At least one identifier is required."""

    mpn: str | None = None
    lcsc: str | None = None
    qty: int = 1

    def __post_init__(self) -> None:
        if not self.mpn and not self.lcsc:
            raise ValueError("a sourcing query requires at least one of 'mpn' or 'lcsc'")
        if self.qty < 1:
            raise ValueError("query qty must be >= 1")
        if self.mpn is not None:
            object.__setattr__(self, "mpn", self.mpn.strip() or None)
        if self.lcsc is not None:
            object.__setattr__(self, "lcsc", self.lcsc.strip() or None)

    @property
    def identifier(self) -> str:
        """Preferred human-readable identifier: LCSC when present, else the MPN."""
        return self.lcsc or self.mpn or ""

    def cache_key(self) -> str:
        """Canonical cache key fragment for this query."""
        return f"qty={self.qty}|mpn={self.mpn or ''}|lcsc={self.lcsc or ''}"

    def to_dict(self) -> dict[str, Any]:
        return {"mpn": self.mpn, "lcsc": self.lcsc, "qty": self.qty}


@dataclass(frozen=True, slots=True)
class OfferPrice:
    """One vendor price break in integer minor currency units."""

    qty: int
    unit_price_minor: int

    def to_dict(self) -> dict[str, int]:
        return {"qty": self.qty, "unit_price_minor": self.unit_price_minor}


@dataclass(frozen=True, slots=True)
class VendorOffer:
    """A normalized vendor offer before it becomes a frozen IR ``Offer``.

    ``vendor`` is the adapter identity (``lcsc``, ``mouser``, ``digikey`` or ``nexar``). The IR
    ``Offer.vendor`` enum has no ``nexar`` member, so :mod:`atomc_plugin_sourcing.normalize`
    maps it to ``"other"`` while keeping the adapter identity in the query report.
    """

    vendor: str
    sku: str
    stock: int
    moq: int
    price_breaks: tuple[OfferPrice, ...]
    currency: str
    fetched_at: datetime
    lead_time_days: int | None = None
    url: str | None = None
    mpn: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "vendor": self.vendor,
            "mpn": self.mpn,
            "sku": self.sku,
            "stock": self.stock,
            "moq": self.moq,
            "lead_time_days": self.lead_time_days,
            "price_breaks": [price.to_dict() for price in self.price_breaks],
            "currency": self.currency,
            "fetched_at": format_timestamp(self.fetched_at),
            "url": self.url,
        }


@dataclass(frozen=True, slots=True)
class AdapterResult:
    """Outcome of one adapter query.

    ``OK`` means a response was parsed; an empty ``offers`` list means the vendor genuinely
    returned no matches. ``UNAVAILABLE`` means no live data could be obtained (missing
    credentials, unreachable endpoint, rejected auth). ``ERROR`` means a live response was
    malformed or otherwise untrustworthy. Neither failure status ever carries offers.
    """

    vendor: str
    status: AdapterStatus
    offers: tuple[VendorOffer, ...] = field(default_factory=tuple)
    message: str | None = None
    evidence: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    fetched_at: datetime = field(default_factory=utcnow)
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "vendor": self.vendor,
            "status": self.status,
            "cached": self.cached,
            "message": self.message,
            "evidence": list(self.evidence),
            "fetched_at": format_timestamp(self.fetched_at),
            "offers": [offer.to_dict() for offer in self.offers],
        }
