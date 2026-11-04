"""``layout`` domain node — outline, placements, test pads, holes and keepouts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import (
    AngleDeg,
    AtomcModel,
    IrId,
    LengthMm,
    NodeMeta,
    Point2,
    Polygon,
    Sha256,
)


class LayoutSource(AtomcModel):
    kind: Literal["kicad_pcb"]
    path: str
    sha256: Sha256 | None = None


class Outline(AtomcModel):
    polygon: Polygon
    thickness_mm: LengthMm = 1.6


class Placement(AtomcModel):
    component_ref: IrId
    x: LengthMm
    y: LengthMm
    rotation_deg: AngleDeg = 0
    side: Literal["top", "bottom"]


class TestPad(AtomcModel):
    id: IrId
    net_ref: IrId
    x: LengthMm
    y: LengthMm
    side: Literal["top", "bottom"] = "bottom"
    diameter_mm: LengthMm = 1.0
    kind: Literal["pogo", "edge", "tag_connect"] = "pogo"
    label: str | None = None


class Hole(AtomcModel):
    id: IrId
    x: LengthMm
    y: LengthMm
    diameter_mm: LengthMm
    plated: bool = False


class Keepout(AtomcModel):
    id: IrId
    polygon: Polygon
    side: Literal["top", "bottom"]
    kind: Literal["component", "copper", "pogo"]


class Layout(AtomcModel):
    meta_: NodeMeta = Field(alias="_meta")
    source: LayoutSource | None = None
    outline: Outline
    layers: int = Field(default=2, ge=1)
    placements: list[Placement] = Field(default_factory=list)
    test_pads: list[TestPad] = Field(default_factory=list)
    mounting_holes: list[Hole] = Field(default_factory=list)
    keepouts: list[Keepout] = Field(default_factory=list)


# Re-exported for callers that build outlines from raw coordinates.
Point = Point2
