"""``fabrication`` domain node — PCB spec and fab quotes."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import AtomcModel, DurationDays, IrId, LengthMm, MoneyMinor, NodeMeta, Timestamp


class PcbSpec(AtomcModel):
    layers: int = Field(ge=1)
    width_mm: LengthMm = Field(gt=0)
    height_mm: LengthMm = Field(gt=0)
    thickness_mm: LengthMm = Field(gt=0)
    finish: Literal["HASL", "LF-HASL", "ENIG"]
    color: str
    qty: int = Field(ge=1)


class Assembly(AtomcModel):
    side: Literal["top", "bottom", "both"]
    parts_count: int = Field(ge=0)


class FabQuote(AtomcModel):
    id: IrId
    fab: Literal["jlcpcb", "pcbway", "other"]
    total_minor: MoneyMinor = Field(ge=0)
    currency: str = "USD"
    lead_time_days: DurationDays
    fetched_at: Timestamp
    breakdown: dict[str, int] = Field(default_factory=dict)
    url: str | None = None


class Fabrication(AtomcModel):
    meta_: NodeMeta = Field(alias="_meta")
    pcb: PcbSpec
    assembly: Assembly | None = None
    quotes: list[FabQuote] = Field(default_factory=list)
