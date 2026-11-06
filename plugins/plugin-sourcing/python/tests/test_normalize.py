"""Normalization into the frozen IR Offer model."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from atomc_core_ir import Offer
from atomc_plugin_sourcing.errors import NormalizationError
from atomc_plugin_sourcing.models import OfferPrice, VendorOffer
from atomc_plugin_sourcing.normalize import offer_id_for, to_ir_offer, to_ir_offers

NOW = datetime(2026, 11, 5, 12, 0, 0, tzinfo=UTC)


def make_offer(**overrides: object) -> VendorOffer:
    data: dict[str, object] = {
        "vendor": "mouser",
        "sku": "511-STM32F411CEU6",
        "stock": 320,
        "moq": 1,
        "price_breaks": (OfferPrice(qty=1, unit_price_minor=45),),
        "currency": "USD",
        "fetched_at": NOW,
        "lead_time_days": 7,
        "url": "https://example.invalid/part",
        "mpn": "STM32F411CEU6",
    }
    data.update(overrides)
    return VendorOffer(**data)  # type: ignore[arg-type]


def test_normalizes_to_frozen_ir_offer() -> None:
    offer = to_ir_offer(make_offer(), "offer:U1_mouser_511-STM32F411CEU6")
    assert isinstance(offer, Offer)
    assert offer.vendor == "mouser"
    assert offer.sku == "511-STM32F411CEU6"
    assert offer.stock == 320
    assert offer.price_breaks[0].unit_price_minor == 45
    dumped = offer.model_dump(mode="json")
    assert dumped["fetched_at"] == "2026-11-05T12:00:00Z"


def test_nexar_maps_to_ir_other_vendor() -> None:
    offer = to_ir_offer(make_offer(vendor="nexar", sku="C1S-STM32F411CEU6"), "offer:U1_nexar_C1S")
    assert offer.vendor == "other"


def test_unknown_vendor_is_surfaced_not_coerced() -> None:
    with pytest.raises(NormalizationError, match="no frozen IR Offer vendor mapping"):
        to_ir_offer(make_offer(vendor="made-up"), "offer:U1_made-up_SKU")


def test_invalid_offer_is_surfaced_from_pydantic() -> None:
    with pytest.raises(NormalizationError, match="failed IR validation"):
        to_ir_offer(make_offer(stock=-1), "offer:U1_mouser_bad")


def test_offer_ids_are_deterministic_and_unique_for_repeated_skus() -> None:
    assert offer_id_for("bom:U1", "lcsc", "C60442") == "offer:bom_U1_lcsc_C60442"
    assert offer_id_for("bom:U1", "lcsc", "C60442", 1) == "offer:bom_U1_lcsc_C60442_2"

    offers = [
        make_offer(vendor="nexar", sku="same"),
        make_offer(vendor="nexar", sku="same"),
    ]
    normalized = to_ir_offers(offers, "bom:U1")
    assert len({offer.id for offer in normalized}) == 2
    assert normalized[0].sku == normalized[1].sku == "same"
