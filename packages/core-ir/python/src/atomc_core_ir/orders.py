"""``orders`` domain node — carts, placed orders and tracking."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import AtomcModel, IrId, MoneyMinor, NodeMeta, Timestamp


class OrderLine(AtomcModel):
    sku: str
    qty: int = Field(ge=1)
    unit_price_minor: MoneyMinor = Field(ge=0)


class Tracking(AtomcModel):
    carrier: str
    number: str
    url: str | None = None


class HistoryEntry(AtomcModel):
    at: Timestamp
    status: str
    note: str | None = None


class Order(AtomcModel):
    id: IrId
    vendor: str
    kind: Literal["parts", "pcb", "pcba"]
    status: Literal["draft", "placed", "paid", "shipped", "delivered", "cancelled"]
    lines: list[OrderLine] = Field(default_factory=list)
    total_minor: MoneyMinor = Field(default=0, ge=0)
    currency: str = "USD"
    external_id: str | None = None
    tracking: list[Tracking] = Field(default_factory=list)
    history: list[HistoryEntry] = Field(default_factory=list)


class Orders(AtomcModel):
    meta_: NodeMeta = Field(alias="_meta")
    orders: list[Order] = Field(default_factory=list)
