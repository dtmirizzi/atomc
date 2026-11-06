"""Pure mechanical gate checks over the derived model data.

Each ``check_*`` function is a deterministic function of the derived models: no CAD import, no
file system and no clock. Gate handlers in :mod:`atomc_plugin_cad_jig.plugin` read the IR, derive
the models and hand them to these functions. The gate runner in the daemon fills in the frozen
``GateResult`` metadata (``id``, ``plugin``, ``severity``, timestamps); these functions return the
status, summary, evidence, suggestions and refs.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from .models import (
    Bounds2,
    MechanicalModels,
    Point2,
    _circle_intersects_bounds,
    _point_in_polygon,
    _point_on_outline,
)

Status = Literal["PASS", "FAIL", "SKIP"]

CUTOUT_NOMINAL_MM = 14.0
PITCH_NOMINAL_MM = 19.05
CUTOUT_ALIGN_TOL_MM = 0.05
PITCH_TOL_MM = 0.05
USB_ALIGN_TOL_MM = 0.5
USB_MAX_EDGE_GAP_MM = 6.0
SPACING_EPS_MM = 1e-9
MIN_WALL_MM = 1.0
MIN_CLEARANCE_MM = 0.1


def _result(
    status: Status,
    summary: str,
    *,
    evidence: list[dict[str, Any]] | None = None,
    suggestions: list[dict[str, Any]] | None = None,
    refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "summary": summary,
        "evidence": evidence or [],
        "suggestions": suggestions or [],
        "refs": refs or [],
    }


def _text(message: str) -> dict[str, Any]:
    return {"kind": "text", "message": message}


def _json(data: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "json", "data": data}


def _min_pair_distance(points: list[tuple[float, float]]) -> tuple[float, tuple[int, int]] | None:
    best: float | None = None
    best_pair = (0, 0)
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            distance = math.dist(points[i], points[j])
            if best is None or distance < best:
                best = distance
                best_pair = (i, j)
    if best is None:
        return None
    return best, best_pair


def check_plate_switch_cutouts(models: MechanicalModels) -> dict[str, Any]:
    """Every switch has a cutout of the nominal diameter on the nominal pitch grid."""
    plate = models.plate
    refs = [cutout.switch_ref for cutout in plate.cutouts]
    if not plate.cutouts:
        return _result(
            "FAIL",
            "no switch cutouts were derived from the layout",
            evidence=[_text("expected one cutout per keyboard switch")],
        )

    problems: list[str] = []
    if abs(plate.cutout_mm - CUTOUT_NOMINAL_MM) > CUTOUT_ALIGN_TOL_MM:
        problems.append(f"plate.cutout_mm {plate.cutout_mm:.3f} != nominal {CUTOUT_NOMINAL_MM:.3f}")
    if abs(plate.pitch_mm - PITCH_NOMINAL_MM) > PITCH_TOL_MM:
        problems.append(f"plate.pitch_mm {plate.pitch_mm:.3f} != nominal {PITCH_NOMINAL_MM:.3f}")
    for cutout in plate.cutouts:
        if abs(cutout.diameter_mm - CUTOUT_NOMINAL_MM) > CUTOUT_ALIGN_TOL_MM:
            problems.append(
                f"cutout {cutout.switch_ref} diameter {cutout.diameter_mm:.3f} "
                f"!= {CUTOUT_NOMINAL_MM:.3f}"
            )
        radius = cutout.diameter_mm / 2.0
        if (
            cutout.x - radius < plate.bounds.min_x - CUTOUT_ALIGN_TOL_MM
            or cutout.x + radius > plate.bounds.max_x + CUTOUT_ALIGN_TOL_MM
            or cutout.y - radius < plate.bounds.min_y - CUTOUT_ALIGN_TOL_MM
            or cutout.y + radius > plate.bounds.max_y + CUTOUT_ALIGN_TOL_MM
        ):
            problems.append(f"cutout {cutout.switch_ref} falls outside the plate bounds")

    points = [(cutout.x, cutout.y) for cutout in plate.cutouts]
    measured = _min_pair_distance(points)
    min_distance = measured[0] if measured is not None else None
    if min_distance is None:
        problems.append("fewer than two cutouts; pitch cannot be measured")
    elif abs(min_distance - PITCH_NOMINAL_MM) > PITCH_TOL_MM:
        pair = measured[1] if measured is not None else (0, 0)
        problems.append(
            f"nearest cutout pitch {min_distance:.3f} between "
            f"{plate.cutouts[pair[0]].switch_ref} and {plate.cutouts[pair[1]].switch_ref} "
            f"!= {PITCH_NOMINAL_MM:.3f}"
        )

    evidence = [
        _text(f"cutouts={len(plate.cutouts)} diameter_mm={plate.cutout_mm:.3f}"),
        _json(
            {
                "cutout_mm": plate.cutout_mm,
                "pitch_mm": plate.pitch_mm,
                "nearest_pitch_mm": min_distance,
                "cutout_count": len(plate.cutouts),
            }
        ),
    ]
    if problems:
        return _result(
            "FAIL",
            "; ".join(problems),
            evidence=evidence,
            suggestions=[_text("align the plate cutouts with the IR switch grid")],
            refs=refs,
        )
    return _result(
        "PASS",
        f"{len(plate.cutouts)} switch cutouts at {plate.cutout_mm:.1f} mm "
        f"on {plate.pitch_mm:.2f} mm pitch",
        evidence=evidence,
        refs=refs,
    )


def check_case_usb_cutout_aligned(models: MechanicalModels) -> dict[str, Any]:
    """The USB cutout sits on the connector's board edge and is centred on the connector."""
    case = models.case
    cutout = case.usb_cutout
    refs = [case.connector_ref]
    problems: list[str] = []
    if cutout.edge not in {"left", "right", "top", "bottom"}:
        problems.append(f"unrecognized connector edge {cutout.edge!r}")
    if case.edge_gap_mm > USB_MAX_EDGE_GAP_MM:
        problems.append(
            f"connector {case.connector_ref} is {case.edge_gap_mm:.2f} mm from the board edge "
            f"(> {USB_MAX_EDGE_GAP_MM:.2f} mm); the cutout cannot align with a wall opening"
        )
    connector_axis = (
        case.connector_center.y if cutout.edge in {"left", "right"} else case.connector_center.x
    )
    delta = abs(cutout.center_along_edge_mm - connector_axis)
    if delta > USB_ALIGN_TOL_MM:
        problems.append(
            f"USB cutout centre is {delta:.3f} mm off the connector centre "
            f"(> {USB_ALIGN_TOL_MM} mm)"
        )
    if cutout.width_mm <= 0 or cutout.height_mm <= 0:
        problems.append("USB cutout has a non-positive dimension")
    if cutout.z_center_mm - cutout.height_mm / 2.0 < -case.base_floor_mm:
        problems.append("USB cutout extends below the case floor")
    if cutout.z_center_mm + cutout.height_mm / 2.0 > case.height_mm:
        problems.append("USB cutout extends above the case")

    evidence = [
        _json(
            {
                "connector_ref": case.connector_ref,
                "edge": cutout.edge,
                "edge_gap_mm": case.edge_gap_mm,
                "alignment_delta_mm": delta,
                "cutout_width_mm": cutout.width_mm,
                "cutout_height_mm": cutout.height_mm,
            }
        )
    ]
    if problems:
        return _result(
            "FAIL",
            "; ".join(problems),
            evidence=evidence,
            suggestions=[_text("move the USB cutout onto the connector's edge or recentre it")],
            refs=refs,
        )
    return _result(
        "PASS",
        f"USB-C cutout on {cutout.edge} edge, alignment delta {delta:.3f} mm",
        evidence=evidence,
        refs=refs,
    )


def check_pogo_spacing(models: MechanicalModels) -> dict[str, Any]:
    """All pogo receptacles are at least ``jig.min_pitch_mm`` centre-to-centre apart."""
    jig = models.jig
    refs = [receptacle.pad_ref for receptacle in jig.receptacles]
    points = [(receptacle.x, receptacle.y) for receptacle in jig.receptacles]
    measured = _min_pair_distance(points)
    if measured is None:
        return _result(
            "PASS",
            "fewer than two pogo receptacles; spacing is vacuously satisfied",
            evidence=[_json({"receptacle_count": len(points), "min_pitch_mm": jig.min_pitch_mm})],
        )
    min_distance, (i, j) = measured
    evidence = [
        _json(
            {
                "receptacle_count": len(points),
                "min_distance_mm": min_distance,
                "min_pitch_mm": jig.min_pitch_mm,
                "closest": [jig.receptacles[i].pad_ref, jig.receptacles[j].pad_ref],
            }
        )
    ]
    if min_distance + SPACING_EPS_MM < jig.min_pitch_mm:
        return _result(
            "FAIL",
            (
                f"pogo receptacles {jig.receptacles[i].pad_ref} and {jig.receptacles[j].pad_ref} "
                f"are {min_distance:.3f} mm apart (< {jig.min_pitch_mm:.3f} mm)"
            ),
            evidence=evidence,
            suggestions=[_text("space the test pads so the P75 receptacles fit side by side")],
            refs=[jig.receptacles[i].pad_ref, jig.receptacles[j].pad_ref],
        )
    return _result(
        "PASS",
        f"closest pogo pitch {min_distance:.3f} mm >= {jig.min_pitch_mm:.3f} mm",
        evidence=evidence,
        refs=refs,
    )


def check_jig_no_collision(models: MechanicalModels) -> dict[str, Any]:
    """Pogo drills clear the 2D component/keepout footprint and stay on the board."""
    jig = models.jig
    pcb = models.pcb
    problems: list[str] = []
    refs: list[str] = []
    for receptacle in jig.receptacles:
        radius = receptacle.drill_diameter_mm / 2.0
        refs.append(receptacle.pad_ref)
        if not _point_inside_or_on_outline(receptacle.x, receptacle.y, pcb.outline):
            problems.append(f"pogo receptacle {receptacle.pad_ref} lies off the board")
        for component in pcb.components:
            if _hits(receptacle.x, receptacle.y, radius, component.bounds):
                problems.append(
                    f"pogo drill {receptacle.pad_ref} collides with component "
                    f"{component.component_ref}"
                )
                refs.append(component.component_ref)
        for index, keepout in enumerate(pcb.keepouts):
            if _hits(receptacle.x, receptacle.y, radius, keepout):
                problems.append(f"pogo drill {receptacle.pad_ref} enters keepout #{index}")
    for pin in jig.alignment_pins:
        radius = pin.diameter_mm / 2.0
        refs.append(pin.hole_ref)
        if not _point_inside_or_on_outline(pin.x, pin.y, pcb.outline):
            problems.append(f"alignment pin {pin.hole_ref} lies off the board")
        for receptacle in jig.receptacles:
            distance = math.dist((pin.x, pin.y), (receptacle.x, receptacle.y))
            if distance < radius + receptacle.drill_diameter_mm / 2.0:
                problems.append(
                    f"alignment pin {pin.hole_ref} collides with pogo {receptacle.pad_ref}"
                )

    evidence = [
        _json(
            {
                "receptacles": len(jig.receptacles),
                "alignment_pins": len(jig.alignment_pins),
                "component_footprints": len(pcb.components),
                "keepouts": len(pcb.keepouts),
            }
        )
    ]
    if problems:
        return _result(
            "FAIL",
            "; ".join(problems),
            evidence=evidence,
            suggestions=[_text("move pogo receptacles off components and keepout regions")],
            refs=sorted(dict.fromkeys(refs)),
        )
    return _result(
        "PASS",
        f"{len(jig.receptacles)} pogo drills clear the bottom footprint",
        evidence=evidence,
        refs=sorted(dict.fromkeys(refs)),
    )


def check_enclosure_clearance(models: MechanicalModels) -> dict[str, Any]:
    """The tray has structural walls and the components fit inside the clearance envelope."""
    case = models.case
    pcb = models.pcb
    problems: list[str] = []
    refs: list[str] = []
    if case.wall_mm < MIN_WALL_MM:
        problems.append(f"wall thickness {case.wall_mm:.2f} mm < {MIN_WALL_MM:.2f} mm")
    if case.clearance_mm < MIN_CLEARANCE_MM:
        problems.append(f"clearance {case.clearance_mm:.2f} mm < {MIN_CLEARANCE_MM:.2f} mm")
    for component in pcb.components:
        refs.append(component.component_ref)
        bounds = component.bounds
        if (
            bounds.min_x < case.inner.min_x
            or bounds.min_y < case.inner.min_y
            or bounds.max_x > case.inner.max_x
            or bounds.max_y > case.inner.max_y
        ):
            problems.append(
                f"component {component.component_ref} extends outside the enclosure cavity"
            )
        if component.max_z > case.height_mm - case.clearance_mm:
            problems.append(f"component {component.component_ref} is taller than the case interior")
    evidence = [
        _json(
            {
                "wall_mm": case.wall_mm,
                "clearance_mm": case.clearance_mm,
                "height_mm": case.height_mm,
                "inner_bounds": [
                    case.inner.min_x,
                    case.inner.min_y,
                    case.inner.max_x,
                    case.inner.max_y,
                ],
                "component_count": len(pcb.components),
            }
        )
    ]
    if problems:
        return _result(
            "FAIL",
            "; ".join(problems),
            evidence=evidence,
            suggestions=[
                _text("enlarge the tray or move components inside the clearance envelope")
            ],
            refs=sorted(dict.fromkeys(refs)),
        )
    return _result(
        "PASS",
        (
            f"enclosure wall {case.wall_mm:.1f} mm, clearance {case.clearance_mm:.2f} mm, "
            f"{len(pcb.components)} components fit"
        ),
        evidence=evidence,
        refs=sorted(dict.fromkeys(refs)),
    )


def _point_inside_or_on_outline(x: float, y: float, polygon: tuple[Point2, ...]) -> bool:
    return _point_in_polygon(x, y, polygon) or _point_on_outline(x, y, polygon)


def _hits(x: float, y: float, radius: float, bounds: Bounds2) -> bool:
    return _circle_intersects_bounds(x, y, radius, bounds)


__all__ = [
    "check_case_usb_cutout_aligned",
    "check_enclosure_clearance",
    "check_jig_no_collision",
    "check_plate_switch_cutouts",
    "check_pogo_spacing",
]
