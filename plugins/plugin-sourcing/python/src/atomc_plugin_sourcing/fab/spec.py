"""Derive the PCB fabrication spec and budget from the system IR.

The frozen ``fabrication`` node has no budget field, so the fabrication gate uses the project
budget at ``/sourcing/budget.total_minor`` when present and otherwise a documented default
threshold. The PCB spec is read from ``/fabrication/pcb`` when it exists; otherwise it is derived
from the board outline in ``/layout`` (layers, outline bbox, thickness) with documented defaults
for the fields the layout does not carry (finish, solder-mask color) and the build quantity from
``/sourcing/build_qty``.

No ``/fabrication`` node is written into the examples: the spec is computed on demand.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from atomc_core_ir import Assembly, PcbSpec

__all__ = [
    "DEFAULT_COLOR",
    "DEFAULT_FAB_BUDGET_MINOR",
    "DEFAULT_FINISH",
    "DEFAULT_PCB_SPEC",
    "DEFAULT_QTY",
    "budget_for_ir",
    "pcb_spec_for_ir",
    "spec_from_mapping",
]

DEFAULT_FINISH = "HASL"
DEFAULT_COLOR = "green"
DEFAULT_QTY = 5
DEFAULT_FAB_BUDGET_MINOR = 10_000  # USD 100.00


def _default_spec() -> PcbSpec:
    return PcbSpec(
        layers=2,
        width_mm=80.0,
        height_mm=80.0,
        thickness_mm=1.6,
        finish=DEFAULT_FINISH,
        color=DEFAULT_COLOR,
        qty=DEFAULT_QTY,
    )


DEFAULT_PCB_SPEC = _default_spec()


def spec_from_mapping(value: Mapping[str, Any]) -> PcbSpec:
    """Validate a caller-supplied spec mapping into the frozen :class:`PcbSpec`."""
    return PcbSpec.model_validate(dict(value))


def assembly_from_mapping(value: Mapping[str, Any] | None) -> Assembly | None:
    """Validate a caller-supplied assembly mapping (``None`` passes through)."""
    if value is None:
        return None
    return Assembly.model_validate(dict(value))


def _layout_bbox(layout: Mapping[str, Any]) -> tuple[float, float] | None:
    outline = layout.get("outline")
    if not isinstance(outline, Mapping):
        return None
    polygon = outline.get("polygon")
    if not isinstance(polygon, list) or len(polygon) < 3:
        return None
    xs: list[float] = []
    ys: list[float] = []
    for point in polygon:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return None
        try:
            xs.append(float(point[0]))
            ys.append(float(point[1]))
        except TypeError, ValueError:
            return None
    if not xs or not ys:
        return None
    return max(xs) - min(xs), max(ys) - min(ys)


def _positive_int(value: Any, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return default
    return value


def _positive_float(value: Any, default: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return default
    return float(value)


def pcb_spec_for_ir(document: Mapping[str, Any] | None) -> tuple[PcbSpec, list[str]]:
    """Return ``(spec, evidence)`` for a project document.

    ``/fabrication/pcb`` wins when present; otherwise the spec is derived from ``/layout`` and
    documented defaults. The returned evidence explains every derived field so the tool report
    never implies data that is not in the IR.
    """
    if not isinstance(document, Mapping):
        return DEFAULT_PCB_SPEC, ["IR root unavailable; using the documented default PCB spec"]
    fabrication = document.get("fabrication")
    if isinstance(fabrication, Mapping):
        pcb = fabrication.get("pcb")
        if isinstance(pcb, Mapping):
            return spec_from_mapping(pcb), ["pcb spec read from /fabrication/pcb"]

    layout = document.get("layout")
    if not isinstance(layout, Mapping):
        return DEFAULT_PCB_SPEC, [
            "/layout is absent; using the documented default PCB spec "
            f"({DEFAULT_PCB_SPEC.layers} layers, "
            f"{DEFAULT_PCB_SPEC.width_mm}x{DEFAULT_PCB_SPEC.height_mm} mm, "
            f"{DEFAULT_PCB_SPEC.thickness_mm} mm, qty {DEFAULT_PCB_SPEC.qty})"
        ]

    evidence: list[str] = []
    layers = _positive_int(layout.get("layers"), DEFAULT_PCB_SPEC.layers)
    if layout.get("layers") != layers:
        evidence.append(f"/layout/layers missing or invalid; defaulting to {layers}")

    bbox = _layout_bbox(layout)
    if bbox is None:
        width, height = DEFAULT_PCB_SPEC.width_mm, DEFAULT_PCB_SPEC.height_mm
        evidence.append(
            f"/layout/outline is missing or degenerate; defaulting to {width}x{height} mm"
        )
    else:
        width, height = bbox
        evidence.append(f"board size {width}x{height} mm derived from /layout/outline bbox")

    thickness = DEFAULT_PCB_SPEC.thickness_mm
    outline = layout.get("outline")
    if isinstance(outline, Mapping):
        thickness = _positive_float(outline.get("thickness_mm"), DEFAULT_PCB_SPEC.thickness_mm)
    if thickness != DEFAULT_PCB_SPEC.thickness_mm:
        evidence.append(f"board thickness {thickness} mm read from /layout/outline/thickness_mm")
    else:
        evidence.append(f"board thickness defaulted to {thickness} mm")

    sourcing = document.get("sourcing")
    qty = DEFAULT_PCB_SPEC.qty
    if isinstance(sourcing, Mapping):
        qty = _positive_int(sourcing.get("build_qty"), DEFAULT_PCB_SPEC.qty)
    evidence.append(f"build quantity {qty} from /sourcing/build_qty")
    evidence.append(
        f"finish {DEFAULT_FINISH!r} and color {DEFAULT_COLOR!r} are documented defaults "
        "(not present in /layout)"
    )
    spec = PcbSpec(
        layers=layers,
        width_mm=width,
        height_mm=height,
        thickness_mm=thickness,
        finish=DEFAULT_FINISH,
        color=DEFAULT_COLOR,
        qty=qty,
    )
    return spec, evidence


def budget_for_ir(document: Mapping[str, Any] | None) -> tuple[int, str]:
    """Return ``(budget_minor, source)`` for the fabrication gate.

    Prefers the project budget at ``/sourcing/budget.total_minor``; falls back to the documented
    default threshold so the gate is always runnable. The source string is surfaced as evidence.
    """
    if isinstance(document, Mapping):
        sourcing = document.get("sourcing")
        if isinstance(sourcing, Mapping):
            budget = sourcing.get("budget")
            if isinstance(budget, Mapping):
                total = budget.get("total_minor")
                if isinstance(total, int) and not isinstance(total, bool) and total >= 0:
                    return total, "project budget /sourcing/budget.total_minor"
    return (
        DEFAULT_FAB_BUDGET_MINOR,
        f"documented default fabrication budget {DEFAULT_FAB_BUDGET_MINOR} minor units",
    )
