"""``mechanical`` domain node — enclosure, plate, pogo jig and mechanical checks."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import (
    Artifact,
    AtomcModel,
    IrId,
    LengthMm,
    NodeMeta,
    Point3,
)


class BBox(AtomcModel):
    min: Point3
    max: Point3


class ComponentBBox(AtomcModel):
    component_ref: IrId
    min: Point3
    max: Point3


class Enclosure(AtomcModel):
    kind: Literal["tray", "sandwich", "none"]
    wall_mm: LengthMm
    clearance_mm: LengthMm
    params: dict[str, object] = Field(default_factory=dict)


class Plate(AtomcModel):
    thickness_mm: LengthMm = 1.5
    cutout_mm: LengthMm = 14.0
    pitch_mm: LengthMm = 19.05
    material: str | None = None


class Jig(AtomcModel):
    pogo_part: str = "P75-E2"
    min_pitch_mm: LengthMm = 2.54
    plate_thickness_mm: LengthMm
    spring_force_n: float | None = Field(default=None, ge=0)
    alignment: Literal["mounting_holes", "pins"]


class MechCheck(AtomcModel):
    id: IrId
    kind: Literal["collision", "clearance", "pogo_spacing", "cutout"]
    status: Literal["pass", "fail"]
    detail: str | None = None


class Mechanical(AtomcModel):
    meta_: NodeMeta = Field(alias="_meta")
    pcb_bbox: BBox | None = None
    component_bboxes: list[ComponentBBox] = Field(default_factory=list)
    enclosure: Enclosure | None = None
    plate: Plate | None = None
    jig: Jig | None = None
    artifacts: list[Artifact] = Field(default_factory=list)
    checks: list[MechCheck] = Field(default_factory=list)
