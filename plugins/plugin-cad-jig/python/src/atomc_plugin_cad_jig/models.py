"""Pure parametric model derivation for the cad-jig plugin.

Everything here is plain arithmetic over the system IR: no CAD import happens until
``cad.generate`` actually builds solids. The derived models are the single source of truth for
both the mechanical gates and the geometry builder, so a gate can verify a design without a CAD
toolchain installed.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .errors import ModelDerivationError

DEFAULT_PLATE_THICKNESS_MM = 1.5
DEFAULT_CUTOUT_MM = 14.0
DEFAULT_PITCH_MM = 19.05
DEFAULT_WALL_MM = 2.0
DEFAULT_CLEARANCE_MM = 0.4
DEFAULT_BASE_FLOOR_MM = 2.0
DEFAULT_POGO_PART = "P75-E2"
DEFAULT_MIN_PITCH_MM = 2.54
DEFAULT_JIG_THICKNESS_MM = 5.0
DEFAULT_PCB_THICKNESS_MM = 1.6
DEFAULT_USB_WIDTH_MM = 9.0
DEFAULT_USB_HEIGHT_MM = 3.2


@dataclass(frozen=True)
class Point2:
    x: float
    y: float


@dataclass(frozen=True)
class Bounds2:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    @property
    def center_x(self) -> float:
        return (self.min_x + self.max_x) / 2.0

    @property
    def center_y(self) -> float:
        return (self.min_y + self.max_y) / 2.0


@dataclass(frozen=True)
class SwitchCutout:
    switch_ref: str
    x: float
    y: float
    diameter_mm: float


@dataclass(frozen=True)
class PlateModel:
    bounds: Bounds2
    thickness_mm: float
    cutout_mm: float
    pitch_mm: float
    material: str | None
    cutouts: tuple[SwitchCutout, ...]


@dataclass(frozen=True)
class UsbCutout:
    edge: str
    center_along_edge_mm: float
    width_mm: float
    height_mm: float
    z_center_mm: float


@dataclass(frozen=True)
class CaseModel:
    outer: Bounds2
    inner: Bounds2
    wall_mm: float
    clearance_mm: float
    base_floor_mm: float
    height_mm: float
    usb_cutout: UsbCutout
    connector_ref: str
    connector_center: Point2
    edge_gap_mm: float


@dataclass(frozen=True)
class PogoReceptacle:
    pad_ref: str
    x: float
    y: float
    pad_diameter_mm: float
    drill_diameter_mm: float


@dataclass(frozen=True)
class AlignmentPin:
    hole_ref: str
    x: float
    y: float
    diameter_mm: float


@dataclass(frozen=True)
class JigModel:
    pcb_bounds: Bounds2
    plate_thickness_mm: float
    pogo_part: str
    min_pitch_mm: float
    receptacles: tuple[PogoReceptacle, ...]
    alignment_pins: tuple[AlignmentPin, ...]


@dataclass(frozen=True)
class ComponentFootprint:
    component_ref: str
    bounds: Bounds2
    min_z: float
    max_z: float


@dataclass(frozen=True)
class PcbModel:
    bounds: Bounds2
    outline: tuple[Point2, ...]
    thickness_mm: float
    components: tuple[ComponentFootprint, ...]
    keepouts: tuple[Bounds2, ...]


@dataclass(frozen=True)
class MechanicalModels:
    plate: PlateModel
    case: CaseModel
    jig: JigModel
    pcb: PcbModel


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ModelDerivationError(field, "expected an object")
    return value


def _sequence(value: Any, field: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ModelDerivationError(field, "expected an array")
    return value


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelDerivationError(field, "expected a number")
    number = float(value)
    if not math.isfinite(number):
        raise ModelDerivationError(field, "expected a finite number")
    return number


def _point(value: Any, field: str) -> Point2:
    pair = _sequence(value, field)
    if len(pair) < 2:
        raise ModelDerivationError(field, "expected [x, y]")
    return Point2(_number(pair[0], f"{field}/0"), _number(pair[1], f"{field}/1"))


def _point3(value: Any, field: str) -> tuple[Point2, float]:
    triple = _sequence(value, field)
    if len(triple) < 2:
        raise ModelDerivationError(field, "expected [x, y, z]")
    point = Point2(_number(triple[0], f"{field}/0"), _number(triple[1], f"{field}/1"))
    z = _number(triple[2], f"{field}/2") if len(triple) > 2 else 0.0
    return point, z


def _bbox_from_points(points: Sequence[Point2], field: str) -> Bounds2:
    if not points:
        raise ModelDerivationError(field, "outline is empty")
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    return Bounds2(min(xs), min(ys), max(xs), max(ys))


def _bbox_from_value(value: Any, field: str) -> Bounds2:
    obj = _mapping(value, field)
    return Bounds2(
        _number(obj.get("min_x"), f"{field}/min_x"),
        _number(obj.get("min_y"), f"{field}/min_y"),
        _number(obj.get("max_x"), f"{field}/max_x"),
        _number(obj.get("max_y"), f"{field}/max_y"),
    )


def _bounds_from_minmax(min_value: Any, max_value: Any, field: str) -> Bounds2:
    minimum = _point(min_value, f"{field}/min")
    maximum = _point(max_value, f"{field}/max")
    return Bounds2(minimum.x, minimum.y, maximum.x, maximum.y)


def _point_in_polygon(x: float, y: float, polygon: Sequence[Point2]) -> bool:
    """Ray-casting point-in-polygon test (boundary hits are not guaranteed either way)."""
    inside = False
    count = len(polygon)
    if count < 3:
        return False
    j = count - 1
    for i in range(count):
        xi, yi = polygon[i].x, polygon[i].y
        xj, yj = polygon[j].x, polygon[j].y
        crosses = (yi > y) != (yj > y)
        if crosses and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _circle_intersects_bounds(x: float, y: float, radius: float, bounds: Bounds2) -> bool:
    nearest_x = min(max(x, bounds.min_x), bounds.max_x)
    nearest_y = min(max(y, bounds.min_y), bounds.max_y)
    return math.hypot(x - nearest_x, y - nearest_y) < radius


def _point_segment_distance(px: float, py: float, a: Point2, b: Point2) -> float:
    dx, dy = b.x - a.x, b.y - a.y
    length_sq = dx * dx + dy * dy
    if length_sq == 0.0:
        return math.hypot(px - a.x, py - a.y)
    t = max(0.0, min(1.0, ((px - a.x) * dx + (py - a.y) * dy) / length_sq))
    return math.hypot(px - (a.x + t * dx), py - (a.y + t * dy))


def _point_on_outline(x: float, y: float, polygon: Sequence[Point2], tol: float = 1e-9) -> bool:
    count = len(polygon)
    for i in range(count):
        if _point_segment_distance(x, y, polygon[i], polygon[(i + 1) % count]) <= tol:
            return True
    return False


def _layout(ir: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(ir.get("layout"), "/layout")


def _mechanical(ir: Mapping[str, Any]) -> Mapping[str, Any]:
    value = ir.get("mechanical")
    return _mapping(value, "/mechanical") if value is not None else {}


def _outline(layout: Mapping[str, Any]) -> tuple[tuple[Point2, ...], Bounds2, float]:
    outline = _mapping(layout.get("outline"), "/layout/outline")
    polygon = tuple(
        _point(p, "/layout/outline/polygon")
        for p in _sequence(outline.get("polygon"), "/layout/outline/polygon")
    )
    if len(polygon) < 3:
        raise ModelDerivationError("/layout/outline/polygon", "need at least 3 vertices")
    thickness = outline.get("thickness_mm", DEFAULT_PCB_THICKNESS_MM)
    return (
        polygon,
        _bbox_from_points(polygon, "/layout/outline/polygon"),
        _number(thickness, "/layout/outline/thickness_mm"),
    )


def _pcb_bounds(mechanical: Mapping[str, Any], outline_bounds: Bounds2) -> Bounds2:
    value = mechanical.get("pcb_bbox")
    if value is None:
        return outline_bounds
    obj = _mapping(value, "/mechanical/pcb_bbox")
    return _bounds_from_minmax(obj.get("min"), obj.get("max"), "/mechanical/pcb_bbox")


def _placements(layout: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    raw = layout.get("placements", [])
    for index, entry in enumerate(_sequence(raw, "/layout/placements")):
        placement = _mapping(entry, f"/layout/placements/{index}")
        ref = placement.get("component_ref")
        if isinstance(ref, str):
            result[ref] = placement
    return result


def _component_bboxes(mechanical: Mapping[str, Any]) -> dict[str, ComponentFootprint]:
    result: dict[str, ComponentFootprint] = {}
    raw = mechanical.get("component_bboxes", [])
    for index, entry in enumerate(_sequence(raw, "/mechanical/component_bboxes")):
        bbox = _mapping(entry, f"/mechanical/component_bboxes/{index}")
        ref = bbox.get("component_ref")
        if not isinstance(ref, str):
            raise ModelDerivationError(
                f"/mechanical/component_bboxes/{index}/component_ref", "expected an id"
            )
        minimum, min_z = _point3(bbox.get("min"), f"/mechanical/component_bboxes/{index}/min")
        maximum, max_z = _point3(bbox.get("max"), f"/mechanical/component_bboxes/{index}/max")
        result[ref] = ComponentFootprint(
            ref,
            Bounds2(minimum.x, minimum.y, maximum.x, maximum.y),
            min_z,
            max_z,
        )
    return result


def _keepouts(layout: Mapping[str, Any]) -> tuple[Bounds2, ...]:
    result: list[Bounds2] = []
    for index, entry in enumerate(_sequence(layout.get("keepouts", []), "/layout/keepouts")):
        keepout = _mapping(entry, f"/layout/keepouts/{index}")
        if "min" in keepout and "max" in keepout:
            result.append(
                _bounds_from_minmax(
                    keepout.get("min"), keepout.get("max"), f"/layout/keepouts/{index}"
                )
            )
        elif all(key in keepout for key in ("x", "y", "width_mm", "height_mm")):
            x = _number(keepout.get("x"), f"/layout/keepouts/{index}/x")
            y = _number(keepout.get("y"), f"/layout/keepouts/{index}/y")
            width = _number(keepout.get("width_mm"), f"/layout/keepouts/{index}/width_mm")
            height = _number(keepout.get("height_mm"), f"/layout/keepouts/{index}/height_mm")
            result.append(Bounds2(x, y, x + width, y + height))
        # Unrecognized keepout shapes are ignored rather than guessed.
    return tuple(result)


def _plate_settings(mechanical: Mapping[str, Any]) -> tuple[float, float, float, str | None]:
    value = mechanical.get("plate")
    if value is None:
        return DEFAULT_PLATE_THICKNESS_MM, DEFAULT_CUTOUT_MM, DEFAULT_PITCH_MM, None
    plate = _mapping(value, "/mechanical/plate")
    return (
        _number(
            plate.get("thickness_mm", DEFAULT_PLATE_THICKNESS_MM),
            "/mechanical/plate/thickness_mm",
        ),
        _number(plate.get("cutout_mm", DEFAULT_CUTOUT_MM), "/mechanical/plate/cutout_mm"),
        _number(plate.get("pitch_mm", DEFAULT_PITCH_MM), "/mechanical/plate/pitch_mm"),
        plate.get("material") if isinstance(plate.get("material"), str) else None,
    )


def _enclosure_settings(mechanical: Mapping[str, Any]) -> tuple[float, float, float]:
    value = mechanical.get("enclosure")
    if value is None:
        return DEFAULT_WALL_MM, DEFAULT_CLEARANCE_MM, DEFAULT_BASE_FLOOR_MM
    enclosure = _mapping(value, "/mechanical/enclosure")
    kind = enclosure.get("kind", "tray")
    if kind == "none":
        raise ModelDerivationError(
            "/mechanical/enclosure/kind", "enclosure kind 'none' has no case"
        )
    return (
        _number(enclosure.get("wall_mm", DEFAULT_WALL_MM), "/mechanical/enclosure/wall_mm"),
        _number(
            enclosure.get("clearance_mm", DEFAULT_CLEARANCE_MM),
            "/mechanical/enclosure/clearance_mm",
        ),
        _number(
            _mapping(enclosure.get("params", {}), "params").get(
                "base_floor_mm", DEFAULT_BASE_FLOOR_MM
            ),
            "/mechanical/enclosure/params/base_floor_mm",
        ),
    )


def _jig_settings(mechanical: Mapping[str, Any]) -> tuple[float, str, float]:
    value = mechanical.get("jig")
    if value is None:
        return DEFAULT_JIG_THICKNESS_MM, DEFAULT_POGO_PART, DEFAULT_MIN_PITCH_MM
    jig = _mapping(value, "/mechanical/jig")
    part = jig.get("pogo_part", DEFAULT_POGO_PART)
    return (
        _number(
            jig.get("plate_thickness_mm", DEFAULT_JIG_THICKNESS_MM),
            "/mechanical/jig/plate_thickness_mm",
        ),
        part if isinstance(part, str) else DEFAULT_POGO_PART,
        _number(jig.get("min_pitch_mm", DEFAULT_MIN_PITCH_MM), "/mechanical/jig/min_pitch_mm"),
    )


def _switch_refs(ir: Mapping[str, Any]) -> list[str]:
    keyboard = ir.get("keyboard")
    if isinstance(keyboard, Mapping):
        keys = _sequence(keyboard.get("keys", []), "/keyboard/keys")
        refs = [_mapping(key, "/keyboard/keys/*").get("switch_ref") for key in keys]
        resolved = [ref for ref in refs if isinstance(ref, str)]
        if resolved:
            return list(dict.fromkeys(resolved))
    components = _mapping(ir.get("electrical"), "/electrical").get("components", [])
    fallback: list[str] = []
    for entry in _sequence(components, "/electrical/components"):
        component = _mapping(entry, "/electrical/components/*")
        designator = component.get("designator")
        footprint = component.get("footprint")
        ref = component.get("id")
        if not isinstance(ref, str):
            continue
        if (isinstance(designator, str) and designator.startswith("SW")) or (
            isinstance(footprint, str) and "Switch_Keyboard" in footprint
        ):
            fallback.append(ref)
    return list(dict.fromkeys(fallback))


def derive_plate(ir: Mapping[str, Any]) -> PlateModel:
    """Derive switch cutout centers from IR switch placements and plate bounds from the outline."""
    layout = _layout(ir)
    mechanical = _mechanical(ir)
    _polygon, outline_bounds, _thickness = _outline(layout)
    thickness, cutout_mm, pitch_mm, material = _plate_settings(mechanical)
    placements = _placements(layout)
    refs = _switch_refs(ir)
    if not refs:
        raise ModelDerivationError("/keyboard/keys", "no switch references found")
    cutouts: list[SwitchCutout] = []
    for ref in refs:
        placement = placements.get(ref)
        if placement is None:
            raise ModelDerivationError("/layout/placements", f"no placement for switch {ref}")
        cutouts.append(
            SwitchCutout(
                switch_ref=ref,
                x=_number(placement.get("x"), f"/layout/placements/{ref}/x"),
                y=_number(placement.get("y"), f"/layout/placements/{ref}/y"),
                diameter_mm=cutout_mm,
            )
        )
    return PlateModel(
        bounds=outline_bounds,
        thickness_mm=thickness,
        cutout_mm=cutout_mm,
        pitch_mm=pitch_mm,
        material=material,
        cutouts=tuple(cutouts),
    )


def _find_usb_connector(
    ir: Mapping[str, Any], layout: Mapping[str, Any], mechanical: Mapping[str, Any]
) -> tuple[str, ComponentFootprint | None, Point2]:
    placements = _placements(layout)
    components = _sequence(
        _mapping(ir.get("electrical"), "/electrical").get("components", []),
        "/electrical/components",
    )
    candidates: list[str] = []
    for entry in components:
        component = _mapping(entry, "/electrical/components/*")
        ref = component.get("id")
        designator = component.get("designator")
        footprint = component.get("footprint")
        if not isinstance(ref, str):
            continue
        if (isinstance(designator, str) and designator.upper() in {"J1", "USB", "USB1"}) or (
            isinstance(footprint, str) and "USB" in footprint.upper()
        ):
            candidates.append(ref)
    if not candidates:
        raise ModelDerivationError("/electrical/components", "no USB connector found")
    # Prefer the first connector with a known placement.
    for ref in candidates:
        placement = placements.get(ref)
        if placement is not None:
            center = Point2(
                _number(placement.get("x"), f"/layout/placements/{ref}/x"),
                _number(placement.get("y"), f"/layout/placements/{ref}/y"),
            )
            return ref, _component_bboxes(mechanical).get(ref), center
    ref = candidates[0]
    raise ModelDerivationError("/layout/placements", f"no placement for USB connector {ref}")


def _nearest_edge(center: Point2, bounds: Bounds2) -> str:
    distances = {
        "left": abs(center.x - bounds.min_x),
        "right": abs(bounds.max_x - center.x),
        "bottom": abs(center.y - bounds.min_y),
        "top": abs(bounds.max_y - center.y),
    }
    return min(distances, key=lambda edge: distances[edge])


def derive_case(ir: Mapping[str, Any]) -> CaseModel:
    """Derive tray walls and a USB-C cutout aligned to the IR connector placement."""
    layout = _layout(ir)
    mechanical = _mechanical(ir)
    _polygon, outline_bounds, _thickness = _outline(layout)
    pcb_bounds = _pcb_bounds(mechanical, outline_bounds)
    wall, clearance, base_floor = _enclosure_settings(mechanical)
    connector_ref, footprint, center = _find_usb_connector(ir, layout, mechanical)
    outer = Bounds2(
        pcb_bounds.min_x - wall - clearance,
        pcb_bounds.min_y - wall - clearance,
        pcb_bounds.max_x + wall + clearance,
        pcb_bounds.max_y + wall + clearance,
    )
    inner = Bounds2(
        pcb_bounds.min_x - clearance,
        pcb_bounds.min_y - clearance,
        pcb_bounds.max_x + clearance,
        pcb_bounds.max_y + clearance,
    )
    edge = _nearest_edge(center, pcb_bounds)
    edge_gap = min(
        abs(center.x - pcb_bounds.min_x),
        abs(pcb_bounds.max_x - center.x),
        abs(center.y - pcb_bounds.min_y),
        abs(pcb_bounds.max_y - center.y),
    )
    if footprint is not None:
        width = footprint.bounds.height if edge in {"left", "right"} else footprint.bounds.width
        height = max(footprint.max_z - footprint.min_z, DEFAULT_USB_HEIGHT_MM)
        z_center = (footprint.min_z + footprint.max_z) / 2.0
    else:
        width = DEFAULT_USB_WIDTH_MM
        height = DEFAULT_USB_HEIGHT_MM
        z_center = height / 2.0
    center_along = center.y if edge in {"left", "right"} else center.x
    max_z = max((comp.max_z for comp in _component_bboxes(mechanical).values()), default=_thickness)
    height_total = base_floor + _thickness + clearance + max_z + clearance
    return CaseModel(
        outer=outer,
        inner=inner,
        wall_mm=wall,
        clearance_mm=clearance,
        base_floor_mm=base_floor,
        height_mm=height_total,
        usb_cutout=UsbCutout(
            edge=edge,
            center_along_edge_mm=center_along,
            width_mm=width,
            height_mm=height,
            z_center_mm=z_center,
        ),
        connector_ref=connector_ref,
        connector_center=center,
        edge_gap_mm=edge_gap,
    )


def derive_jig(ir: Mapping[str, Any]) -> JigModel:
    """Derive pogo receptacle positions from /layout test pads and alignment pins from holes."""
    layout = _layout(ir)
    mechanical = _mechanical(ir)
    polygon, outline_bounds, _thickness = _outline(layout)
    pcb_bounds = _pcb_bounds(mechanical, outline_bounds)
    thickness, part, min_pitch = _jig_settings(mechanical)
    pads = _sequence(layout.get("test_pads", []), "/layout/test_pads")
    pogo_entries = [
        _mapping(entry, "/layout/test_pads/*")
        for entry in pads
        if _mapping(entry, "/layout/test_pads/*").get("kind") == "pogo"
    ]
    if not pogo_entries:
        pogo_entries = [_mapping(entry, "/layout/test_pads/*") for entry in pads]
    if not pogo_entries:
        raise ModelDerivationError("/layout/test_pads", "no test pads for the pogo jig")
    receptacles: list[PogoReceptacle] = []
    for index, pad in enumerate(pogo_entries):
        pad_ref = pad.get("id")
        if not isinstance(pad_ref, str):
            raise ModelDerivationError(f"/layout/test_pads/{index}/id", "expected an id")
        diameter = _number(pad.get("diameter_mm", 1.0), f"/layout/test_pads/{index}/diameter_mm")
        receptacles.append(
            PogoReceptacle(
                pad_ref=pad_ref,
                x=_number(pad.get("x"), f"/layout/test_pads/{index}/x"),
                y=_number(pad.get("y"), f"/layout/test_pads/{index}/y"),
                pad_diameter_mm=diameter,
                drill_diameter_mm=min(diameter + 1.0, min_pitch),
            )
        )
    holes = _sequence(layout.get("mounting_holes", []), "/layout/mounting_holes")
    pins: list[AlignmentPin] = []
    for index, entry in enumerate(holes):
        hole = _mapping(entry, f"/layout/mounting_holes/{index}")
        hole_ref = hole.get("id")
        if not isinstance(hole_ref, str):
            raise ModelDerivationError(f"/layout/mounting_holes/{index}/id", "expected an id")
        x = _number(hole.get("x"), f"/layout/mounting_holes/{index}/x")
        y = _number(hole.get("y"), f"/layout/mounting_holes/{index}/y")
        if not _point_in_polygon(x, y, polygon) and not _point_on_outline(x, y, polygon):
            raise ModelDerivationError(
                f"/layout/mounting_holes/{index}", "mounting hole lies outside the board outline"
            )
        pins.append(
            AlignmentPin(
                hole_ref=hole_ref,
                x=x,
                y=y,
                diameter_mm=_number(
                    hole.get("diameter_mm", 3.2), f"/layout/mounting_holes/{index}/diameter_mm"
                ),
            )
        )
    return JigModel(
        pcb_bounds=pcb_bounds,
        plate_thickness_mm=thickness,
        pogo_part=part,
        min_pitch_mm=min_pitch,
        receptacles=tuple(receptacles),
        alignment_pins=tuple(pins),
    )


def derive_pcb(ir: Mapping[str, Any]) -> PcbModel:
    """PCB footprint projection: outline polygon, component bboxes and keepouts."""
    layout = _layout(ir)
    mechanical = _mechanical(ir)
    polygon, outline_bounds, thickness = _outline(layout)
    pcb_bounds = _pcb_bounds(mechanical, outline_bounds)
    components = tuple(_component_bboxes(mechanical).values())
    return PcbModel(
        bounds=pcb_bounds,
        outline=polygon,
        thickness_mm=thickness,
        components=components,
        keepouts=_keepouts(layout),
    )


def derive_models(ir: Mapping[str, Any]) -> MechanicalModels:
    """Derive every mechanical model in one pass."""
    return MechanicalModels(
        plate=derive_plate(ir),
        case=derive_case(ir),
        jig=derive_jig(ir),
        pcb=derive_pcb(ir),
    )


__all__ = [
    "AlignmentPin",
    "Bounds2",
    "CaseModel",
    "ComponentFootprint",
    "JigModel",
    "MechanicalModels",
    "PcbModel",
    "PlateModel",
    "PogoReceptacle",
    "Point2",
    "SwitchCutout",
    "UsbCutout",
    "derive_case",
    "derive_jig",
    "derive_models",
    "derive_pcb",
    "derive_plate",
]
