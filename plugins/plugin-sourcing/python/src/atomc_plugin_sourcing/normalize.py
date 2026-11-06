"""Normalize vendor offers into the frozen IR ``Offer`` model.

The IR model validates the result; validation errors are raised as
:class:`NormalizationError` rather than coerced or partially written.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from atomc_core_ir import Offer, PriceBreak
from pydantic import ValidationError

from .errors import NormalizationError
from .models import VendorOffer

__all__ = ["IR_VENDOR_MAP", "offer_id_for", "to_ir_offer", "to_ir_offers"]

IR_VENDOR_MAP: dict[str, str] = {
    "lcsc": "lcsc",
    "jlcpcb": "jlcpcb",
    "mouser": "mouser",
    "digikey": "digikey",
    # Nexar is an aggregator; the frozen Offer.vendor enum only has "other" for it.
    "nexar": "other",
    "other": "other",
}

_SLUG = re.compile(r"[^A-Za-z0-9_.\-/]+")


def _slug(value: str) -> str:
    cleaned = _SLUG.sub("_", value.strip())
    cleaned = cleaned.strip("_")
    return cleaned or "offer"


def offer_id_for(prefix: str, vendor: str, sku: str, occurrence: int = 0) -> str:
    """Build a deterministic, IR-valid offer id from a line/query prefix, vendor and SKU."""
    base = f"offer:{_slug(prefix)}_{_slug(vendor)}_{_slug(sku)}"
    if occurrence > 0:
        return f"{base}_{occurrence + 1}"
    return base


def _ir_vendor(vendor: str) -> str:
    mapped = IR_VENDOR_MAP.get(vendor)
    if mapped is None:
        raise NormalizationError(f"vendor {vendor!r} has no frozen IR Offer vendor mapping")
    return mapped


def to_ir_offer(offer: VendorOffer, offer_id: str) -> Offer:
    """Validate one vendor offer as a frozen IR ``Offer``.

    Raises :class:`NormalizationError` with the Pydantic details when any field is invalid.
    """
    try:
        return Offer(
            id=offer_id,
            vendor=_ir_vendor(offer.vendor),
            sku=offer.sku,
            stock=offer.stock,
            lead_time_days=offer.lead_time_days,
            moq=offer.moq,
            price_breaks=[
                PriceBreak(qty=price.qty, unit_price_minor=price.unit_price_minor)
                for price in offer.price_breaks
            ],
            currency=offer.currency,
            fetched_at=offer.fetched_at,
            url=offer.url,
        )
    except ValidationError as exc:
        raise NormalizationError(
            f"vendor offer for {offer.vendor}:{offer.sku} failed IR validation: "
            f"{exc.error_count()} error(s)"
        ) from exc


def to_ir_offers(
    offers: Iterable[VendorOffer],
    prefix: str,
) -> list[Offer]:
    """Normalize a sequence, keeping ids unique when a vendor repeats a SKU."""
    seen: dict[str, int] = {}
    result: list[Offer] = []
    for offer in offers:
        key = f"{offer.vendor}|{offer.sku}"
        occurrence = seen.get(key, 0)
        seen[key] = occurrence + 1
        result.append(to_ir_offer(offer, offer_id_for(prefix, offer.vendor, offer.sku, occurrence)))
    return result
