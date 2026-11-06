"""Deterministic fixtures for the pure optimizer and gate tests."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atomc_core_ir import BomLine, Budget, NodeMeta, Offer, PriceBreak, Sourcing

FIXED_NOW = datetime(2026, 11, 5, 12, 0, 0, tzinfo=UTC)


def repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "examples" / "atomc-pad" / "system_ir.json"
        if candidate.is_file():
            return parent
    raise RuntimeError("could not locate repository root")


def pad_sourcing() -> dict[str, Any]:
    document = json.loads(
        (repo_root() / "examples" / "atomc-pad" / "system_ir.json").read_text(encoding="utf-8")
    )
    return copy.deepcopy(document["sourcing"])


def offer(
    offer_id: str,
    *,
    vendor: str = "lcsc",
    sku: str | None = None,
    stock: int = 100,
    moq: int = 1,
    unit_price_minor: int = 100,
    price_qty: int = 1,
    lead_time_days: int | None = 7,
    currency: str = "USD",
) -> Offer:
    return Offer(
        id=offer_id,
        vendor=vendor,  # type: ignore[arg-type]
        sku=sku or offer_id.split(":", 1)[-1],
        stock=stock,
        lead_time_days=lead_time_days,
        moq=moq,
        price_breaks=[PriceBreak(qty=price_qty, unit_price_minor=unit_price_minor)],
        currency=currency,
        fetched_at=FIXED_NOW,
    )


def bom_line(
    line_id: str = "bom:U1",
    *,
    offers: list[Offer] | None = None,
    qty_per_unit: int = 1,
    chosen_offer_ref: str | None = None,
    mpn: str = "PART-1",
    lcsc: str | None = "C1",
) -> BomLine:
    return BomLine(
        id=line_id,
        component_refs=["comp:U1"],
        mpn=mpn,
        lcsc=lcsc,
        qty_per_unit=qty_per_unit,
        offers=offers or [],
        chosen_offer_ref=chosen_offer_ref,
    )


def sourcing(
    bom: list[BomLine],
    *,
    build_qty: int = 2,
    per_unit_minor: int = 10_000,
    total_minor: int | None = 100_000,
    currency: str = "USD",
) -> Sourcing:
    return Sourcing(
        meta_=NodeMeta(rev=1),
        currency=currency,
        build_qty=build_qty,
        budget=Budget(per_unit_minor=per_unit_minor, total_minor=total_minor),
        bom=bom,
    )


def pad_model() -> Sourcing:
    return Sourcing.model_validate(pad_sourcing())


def add_offer(node: dict[str, Any], line_id: str, new_offer: dict[str, Any]) -> None:
    for line in node["bom"]:
        if line["id"] == line_id:
            line["offers"].append(new_offer)
            return
    raise KeyError(line_id)
