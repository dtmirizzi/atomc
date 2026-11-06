"""Deterministic cart rendering: per-vendor goldens and offer selection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from _orders_helpers import demo_ir
from atomc_plugin_orders.carts import (
    cart_artifact_id,
    cart_lines_from_sourcing,
    choose_unit_price,
    group_by_vendor,
    render_cart,
    select_offer,
)
from atomc_plugin_orders.errors import CartBuildError

FIXTURES = Path(__file__).with_name("fixtures") / "carts"
GOLDEN = {
    "lcsc": "lcsc-cart.csv",
    "jlcpcb": "jlcpcb-cart.csv",
    "mouser": "mouser-cart.csv",
    "digikey": "digikey-cart.csv",
}


def _document() -> dict[str, Any]:
    return demo_ir().model_dump(mode="json", by_alias=True)


def test_choose_unit_price_picks_applicable_break() -> None:
    offer = {
        "price_breaks": [
            {"qty": 1, "unit_price_minor": 420},
            {"qty": 5, "unit_price_minor": 390},
            {"qty": 100, "unit_price_minor": 300},
        ]
    }
    assert choose_unit_price(offer, 1) == 420
    assert choose_unit_price(offer, 5) == 390
    assert choose_unit_price(offer, 99) == 390
    assert choose_unit_price(offer, 100) == 300
    assert choose_unit_price(offer, 10_000) == 300


def test_choose_unit_price_falls_back_to_smallest_break() -> None:
    offer = {"price_breaks": [{"qty": 10, "unit_price_minor": 50}]}
    assert choose_unit_price(offer, 1) == 50
    assert choose_unit_price({"price_breaks": []}, 1) == 0


def test_select_offer_requires_a_chosen_offer() -> None:
    with pytest.raises(CartBuildError, match="no chosen_offer_ref"):
        select_offer({"id": "bom:x", "offers": []})
    with pytest.raises(CartBuildError, match="missing offer"):
        select_offer({"id": "bom:x", "chosen_offer_ref": "offer:missing", "offers": []})


def test_cart_lines_apply_build_qty_and_moq() -> None:
    document = _document()
    lines = cart_lines_from_sourcing(
        document["sourcing"], electrical=document["electrical"], build_qty=5
    )
    by_sku = {line.sku: line for line in lines}
    assert by_sku["C60442"].qty == 5
    assert by_sku["C60442"].unit_price_minor == 390
    assert by_sku["603-RC0603FR-0710KL"].qty == 10
    assert by_sku["C14663"].qty == 20
    assert by_sku["1528-1234-ND"].qty == 5
    assert by_sku["C60442"].designators == ("U1",)
    assert by_sku["C60442"].footprint == "QFN-48"


def test_moq_raises_quantity() -> None:
    document = _document()
    document["sourcing"]["bom"][0]["offers"][0]["moq"] = 50
    lines = cart_lines_from_sourcing(
        document["sourcing"], electrical=document["electrical"], build_qty=1
    )
    assert next(line for line in lines if line.sku == "C60442").qty == 50


def test_group_by_vendor_is_sorted() -> None:
    document = _document()
    lines = cart_lines_from_sourcing(document["sourcing"], electrical=document["electrical"])
    grouped = group_by_vendor(lines)
    assert list(grouped) == ["digikey", "jlcpcb", "lcsc", "mouser"]


@pytest.mark.parametrize("vendor", sorted(GOLDEN))
def test_cart_golden_matches(vendor: str) -> None:
    document = _document()
    lines = cart_lines_from_sourcing(
        document["sourcing"], electrical=document["electrical"], build_qty=5
    )
    grouped = group_by_vendor(lines)
    cart = render_cart(vendor, grouped[vendor])
    expected = (FIXTURES / GOLDEN[vendor]).read_text(encoding="utf-8")
    assert cart.content == expected
    assert cart.filename == GOLDEN[vendor]


def test_render_is_byte_stable() -> None:
    document = _document()
    lines = cart_lines_from_sourcing(document["sourcing"], electrical=document["electrical"])
    grouped = group_by_vendor(lines)
    first = render_cart("lcsc", grouped["lcsc"]).content
    second = render_cart("lcsc", list(reversed(grouped["lcsc"]))).content
    assert first == second


def test_generic_vendor_format() -> None:
    document = _document()
    lines = cart_lines_from_sourcing(document["sourcing"], electrical=document["electrical"])
    line = next(line for line in lines if line.vendor == "mouser")
    generic = render_cart("other", [line])
    assert generic.content.splitlines()[0] == "SKU,Quantity,Vendor,MPN"
    assert "other" in generic.content


def test_empty_or_unpriced_sourcing_fails() -> None:
    with pytest.raises(CartBuildError, match="empty"):
        cart_lines_from_sourcing({"bom": []})
    with pytest.raises(CartBuildError, match="no chosen_offer_ref"):
        cart_lines_from_sourcing(
            {"bom": [{"id": "bom:x", "qty_per_unit": 1, "offers": [], "chosen_offer_ref": None}]}
        )


def test_cart_artifact_id_is_a_valid_ir_id() -> None:
    assert cart_artifact_id("lcsc") == "art:orders_lcsc_cart"
    assert cart_artifact_id("Digi-Key") == "art:orders_digi_key_cart"
