"""``sourcing`` domain node — BOM lines, vendor offers and alternates."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import AtomcModel, DurationDays, IrId, MoneyMinor, NodeMeta, Timestamp

Vendor = Literal["lcsc", "jlcpcb", "mouser", "digikey", "other"]


class PriceBreak(AtomcModel):
    qty: int = Field(ge=1)
    unit_price_minor: MoneyMinor = Field(ge=0)


class Offer(AtomcModel):
    id: IrId
    vendor: Vendor
    sku: str
    stock: int = Field(ge=0)
    lead_time_days: DurationDays | None = None
    moq: int = Field(default=1, ge=1)
    price_breaks: list[PriceBreak] = Field(default_factory=list)
    currency: str = "USD"
    fetched_at: Timestamp
    url: str | None = None


class Alternate(AtomcModel):
    mpn: str
    lcsc: str | None = None
    reason: str | None = None


class BomLine(AtomcModel):
    id: IrId
    component_refs: list[IrId] = Field(default_factory=list)
    mpn: str | None = None
    lcsc: str | None = None
    qty_per_unit: int = Field(ge=1)
    offers: list[Offer] = Field(default_factory=list)
    chosen_offer_ref: IrId | None = None
    alternates: list[Alternate] = Field(default_factory=list)


class Budget(AtomcModel):
    per_unit_minor: MoneyMinor = Field(ge=0)
    total_minor: MoneyMinor | None = Field(default=None, ge=0)


class Sourcing(AtomcModel):
    meta_: NodeMeta = Field(alias="_meta")
    currency: str = "USD"
    build_qty: int = Field(default=1, ge=1)
    budget: Budget | None = None
    bom: list[BomLine] = Field(default_factory=list)
