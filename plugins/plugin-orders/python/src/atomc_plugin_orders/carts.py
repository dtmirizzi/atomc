"""Deterministic per-vendor cart rendering from the frozen ``/sourcing`` node.

The IR stores *offers*, not carts. This module turns each BOM line's chosen offer into a cart
line, groups by vendor and renders the vendor's documented upload format as text. Rendering is
pure and byte-stable so the CSV goldens are meaningful and diffs stay small.

No network or filesystem access happens here; the plugin writes the rendered text itself.

Formats:

* ``lcsc``   — LCSC BOM upload CSV: ``Comment,Designator,Footprint,LCSC Part #,Quantity``
* ``jlcpcb`` — JLCPCB SMT BOM upload CSV: ``Comment,Designator,Footprint,LCSC Part #``
* ``mouser`` — Mouser cart CSV: ``Mouser Part Number,Quantity,Customer Part Number``
* ``digikey``— DigiKey list CSV: ``DigiKey Part Number,Quantity,Customer Reference``
* other     — a generic ``SKU,Quantity,Vendor,MPN`` CSV

These columns follow the public upload formats at the time of writing; they are *not* a claim of
live vendor API support (no vendor is ever contacted by this plugin).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .errors import CartBuildError
from .ledger import slugify

__all__ = [
    "CartFile",
    "CartLine",
    "cart_artifact_id",
    "cart_lines_from_sourcing",
    "choose_unit_price",
    "group_by_vendor",
    "render_cart",
    "select_offer",
]

_SUPPORTED_VENDORS = frozenset({"lcsc", "jlcpcb", "mouser", "digikey", "other"})


@dataclass(frozen=True)
class CartLine:
    """One requested line for a vendor cart."""

    vendor: str
    sku: str
    qty: int
    comment: str
    designators: tuple[str, ...] = ()
    footprint: str = ""
    customer_ref: str = ""
    unit_price_minor: int = 0
    currency: str = "USD"


@dataclass(frozen=True)
class CartFile:
    """A rendered cart file ready to write under the project build directory."""

    vendor: str
    filename: str
    content: str
    line_count: int
    format: str

    @property
    def bytes(self) -> bytes:
        return self.content.encode("utf-8")


def choose_unit_price(offer: Mapping[str, Any], qty: int) -> int:
    """Return the best unit price (minor units) for ``qty`` from an offer's price breaks.

    Chooses the highest price break whose ``qty`` is ``<= qty``; falls back to the smallest
    break; returns ``0`` when the offer declares no price breaks.
    """
    breaks = [
        (int(break_.get("qty", 0)), int(break_.get("unit_price_minor", 0)))
        for break_ in offer.get("price_breaks") or []
        if isinstance(break_, Mapping)
    ]
    if not breaks:
        return 0
    breaks.sort(key=lambda item: item[0])
    applicable = [price for threshold, price in breaks if threshold <= qty]
    if applicable:
        return applicable[-1]
    return breaks[0][1]


def select_offer(bom_line: Mapping[str, Any]) -> dict[str, Any]:
    """Return the chosen offer of a BOM line, or raise :class:`CartBuildError`."""
    chosen_ref = bom_line.get("chosen_offer_ref")
    offers = [offer for offer in bom_line.get("offers") or [] if isinstance(offer, Mapping)]
    if not chosen_ref:
        raise CartBuildError(
            f"BOM line {bom_line.get('id')!r} has no chosen_offer_ref; "
            "run the sourcing optimizer first"
        )
    for offer in offers:
        if offer.get("id") == chosen_ref:
            return dict(offer)
    raise CartBuildError(f"BOM line {bom_line.get('id')!r} references missing offer {chosen_ref!r}")


def _component_lookup(electrical: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if not electrical:
        return {}
    components = electrical.get("components")
    if not isinstance(components, list):
        return {}
    return {
        str(component["id"]): component
        for component in components
        if isinstance(component, Mapping) and component.get("id")
    }


def _customer_ref(bom_line: Mapping[str, Any], designators: tuple[str, ...]) -> str:
    if bom_line.get("mpn"):
        return str(bom_line["mpn"])
    if designators:
        return " ".join(designators)
    return str(bom_line.get("id") or "")


def cart_lines_from_sourcing(
    sourcing: Mapping[str, Any],
    *,
    electrical: Mapping[str, Any] | None = None,
    build_qty: int | None = None,
) -> list[CartLine]:
    """Convert every chosen offer in ``/sourcing`` into a :class:`CartLine`.

    Raises :class:`CartBuildError` when no BOM lines exist or any line lacks a chosen offer.
    """
    bom = sourcing.get("bom")
    if not isinstance(bom, list) or not bom:
        raise CartBuildError(
            "IR /sourcing.bom is empty; refresh sourcing and choose an offer per line first"
        )
    quantity = int(build_qty if build_qty is not None else sourcing.get("build_qty") or 1)
    if quantity < 1:
        raise CartBuildError("build_qty must be >= 1")

    components = _component_lookup(electrical)
    lines: list[CartLine] = []
    failures: list[str] = []
    for index, bom_line in enumerate(bom):
        if not isinstance(bom_line, Mapping):
            failures.append(f"bom[{index}] is not an object")
            continue
        try:
            offer = select_offer(bom_line)
        except CartBuildError as exc:
            failures.append(str(exc))
            continue
        vendor = str(offer.get("vendor") or "other")
        if vendor not in _SUPPORTED_VENDORS:
            vendor = "other"
        qty_per_unit = int(bom_line.get("qty_per_unit") or 1)
        moq = max(1, int(offer.get("moq") or 1))
        qty = max(moq, qty_per_unit * quantity)
        refs = [str(ref) for ref in bom_line.get("component_refs") or []]
        designators = tuple(
            str(components[ref].get("designator") or ref.split(":", 1)[-1]) for ref in refs
        )
        footprint = ""
        for ref in refs:
            candidate = components.get(ref)
            if candidate and candidate.get("footprint"):
                footprint = str(candidate["footprint"])
                break
        lines.append(
            CartLine(
                vendor=vendor,
                sku=str(offer.get("sku") or ""),
                qty=qty,
                comment=str(
                    bom_line.get("mpn") or bom_line.get("lcsc") or bom_line.get("id") or ""
                ),
                designators=designators,
                footprint=footprint,
                customer_ref=_customer_ref(bom_line, designators),
                unit_price_minor=choose_unit_price(offer, qty),
                currency=str(offer.get("currency") or sourcing.get("currency") or "USD"),
            )
        )

    if failures:
        raise CartBuildError("; ".join(failures))
    if not lines:
        raise CartBuildError("no cart lines could be derived from /sourcing")
    return lines


def group_by_vendor(lines: Iterable[CartLine]) -> dict[str, list[CartLine]]:
    """Group cart lines by vendor, sorted deterministically by vendor then SKU."""
    grouped: dict[str, list[CartLine]] = {}
    for line in lines:
        grouped.setdefault(line.vendor, []).append(line)
    for vendor_lines in grouped.values():
        vendor_lines.sort(key=lambda item: (item.sku, item.comment))
    return dict(sorted(grouped.items()))


def _csv_text(header: list[str], rows: list[list[Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


def _designators(line: CartLine) -> str:
    return " ".join(line.designators)


def _render_lcsc(lines: list[CartLine]) -> tuple[str, str]:
    content = _csv_text(
        ["Comment", "Designator", "Footprint", "LCSC Part #", "Quantity"],
        [[line.comment, _designators(line), line.footprint, line.sku, line.qty] for line in lines],
    )
    return "lcsc_bom", content


def _render_jlcpcb(lines: list[CartLine]) -> tuple[str, str]:
    content = _csv_text(
        ["Comment", "Designator", "Footprint", "LCSC Part #"],
        [[line.comment, _designators(line), line.footprint, line.sku] for line in lines],
    )
    return "jlcpcb_bom", content


def _render_mouser(lines: list[CartLine]) -> tuple[str, str]:
    content = _csv_text(
        ["Mouser Part Number", "Quantity", "Customer Part Number"],
        [[line.sku, line.qty, line.customer_ref] for line in lines],
    )
    return "mouser_cart", content


def _render_digikey(lines: list[CartLine]) -> tuple[str, str]:
    content = _csv_text(
        ["DigiKey Part Number", "Quantity", "Customer Reference"],
        [[line.sku, line.qty, line.customer_ref] for line in lines],
    )
    return "digikey_cart", content


def _render_generic(vendor: str, lines: list[CartLine]) -> tuple[str, str]:
    content = _csv_text(
        ["SKU", "Quantity", "Vendor", "MPN"],
        [[line.sku, line.qty, vendor, line.comment] for line in lines],
    )
    return "generic_cart", content


_RENDERERS = {
    "lcsc": _render_lcsc,
    "jlcpcb": _render_jlcpcb,
    "mouser": _render_mouser,
    "digikey": _render_digikey,
}


def render_cart(vendor: str, lines: Iterable[CartLine]) -> CartFile:
    """Render the cart for one vendor in that vendor's upload format.

    Rows are sorted by ``(sku, comment)`` so the output is independent of input order.
    """
    vendor_lines = sorted(lines, key=lambda item: (item.sku, item.comment))
    if not vendor_lines:
        raise CartBuildError(f"cannot render an empty cart for vendor {vendor!r}")
    renderer = _RENDERERS.get(vendor)
    if renderer is None:
        cart_format, content = _render_generic(vendor, vendor_lines)
    else:
        cart_format, content = renderer(vendor_lines)
    slug = slugify(vendor)
    return CartFile(
        vendor=vendor,
        filename=f"{slug}-cart.csv",
        content=content,
        line_count=len(vendor_lines),
        format=cart_format,
    )


def cart_artifact_id(vendor: str) -> str:
    """Stable IR artifact id for a vendor cart file."""
    return f"art:orders_{slugify(vendor)}_cart"
