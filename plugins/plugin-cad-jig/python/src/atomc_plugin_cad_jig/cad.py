"""build123d solid builders for the derived mechanical models.

This module is only imported (and build123d only imported inside the functions) when
``cad.generate`` actually runs. The rest of the plugin stays usable with no CAD toolchain
installed; :func:`build123d_available` reports whether the tool can build anything at all.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from typing import Any

from .models import CaseModel, JigModel, MechanicalModels, PcbModel, PlateModel


class CadUnavailableError(RuntimeError):
    """build123d/OCP is not installed in the running interpreter."""


def build123d_available() -> bool:
    """Whether the optional CAD toolchain can be imported."""
    return importlib.util.find_spec("build123d") is not None


def _require_build123d() -> Any:
    if not build123d_available():
        raise CadUnavailableError("build123d is not installed (install the 'cad' extra)")
    import build123d  # type: ignore[import-not-found]  # lazy: only needed by cad.generate

    return build123d


def _box(min_x: float, min_y: float, max_x: float, max_y: float, z0: float, z1: float) -> Any:
    build123d = _require_build123d()
    if max_x <= min_x or max_y <= min_y or z1 <= z0:
        raise ValueError(f"degenerate box ({min_x}, {min_y})-({max_x}, {max_y}) z=({z0}, {z1})")
    return build123d.Pos(
        (min_x + max_x) / 2.0, (min_y + max_y) / 2.0, (z0 + z1) / 2.0
    ) * build123d.Box(max_x - min_x, max_y - min_y, z1 - z0)


def _cylinder(x: float, y: float, diameter_mm: float, z0: float, z1: float) -> Any:
    build123d = _require_build123d()
    if diameter_mm <= 0 or z1 <= z0:
        raise ValueError(f"degenerate cylinder at ({x}, {y}) d={diameter_mm} z=({z0}, {z1})")
    return build123d.Pos(x, y, (z0 + z1) / 2.0) * build123d.Cylinder(diameter_mm / 2.0, z1 - z0)


def build_plate(models: MechanicalModels) -> Any:
    """Switch plate: outline slab with 14 mm switch cutouts."""
    plate: PlateModel = models.plate
    thickness = plate.thickness_mm
    solid = _box(
        plate.bounds.min_x,
        plate.bounds.min_y,
        plate.bounds.max_x,
        plate.bounds.max_y,
        0.0,
        thickness,
    )
    for cutout in plate.cutouts:
        solid -= _cylinder(cutout.x, cutout.y, cutout.diameter_mm, -0.5, thickness + 0.5)
    return solid


def build_case(models: MechanicalModels) -> Any:
    """Tray case: outer shell minus the cavity and the USB-C cutout."""
    case: CaseModel = models.case
    z0 = -case.base_floor_mm
    z1 = case.height_mm
    outer = _box(case.outer.min_x, case.outer.min_y, case.outer.max_x, case.outer.max_y, z0, z1)
    cavity = _box(
        case.inner.min_x,
        case.inner.min_y,
        case.inner.max_x,
        case.inner.max_y,
        z0 + 1e-3,
        z1 + 1.0,
    )
    solid = outer - cavity
    cutout = case.usb_cutout
    half_width = cutout.width_mm / 2.0
    height = cutout.height_mm
    z_center = cutout.z_center_mm
    if cutout.edge == "left":
        solid -= _box(
            case.outer.min_x - 0.5,
            cutout.center_along_edge_mm - half_width,
            case.inner.min_x + 0.5,
            cutout.center_along_edge_mm + half_width,
            z_center - height / 2.0,
            z_center + height / 2.0,
        )
    elif cutout.edge == "right":
        solid -= _box(
            case.inner.max_x - 0.5,
            cutout.center_along_edge_mm - half_width,
            case.outer.max_x + 0.5,
            cutout.center_along_edge_mm + half_width,
            z_center - height / 2.0,
            z_center + height / 2.0,
        )
    elif cutout.edge == "bottom":
        solid -= _box(
            cutout.center_along_edge_mm - half_width,
            case.outer.min_y - 0.5,
            cutout.center_along_edge_mm + half_width,
            case.inner.min_y + 0.5,
            z_center - height / 2.0,
            z_center + height / 2.0,
        )
    else:
        solid -= _box(
            cutout.center_along_edge_mm - half_width,
            case.inner.max_y - 0.5,
            cutout.center_along_edge_mm + half_width,
            case.outer.max_y + 0.5,
            z_center - height / 2.0,
            z_center + height / 2.0,
        )
    return solid


def build_jig(models: MechanicalModels) -> Any:
    """Pogo-pin bed of nails: jig plate with receptacle and alignment-pin holes."""
    jig: JigModel = models.jig
    bounds = jig.pcb_bounds
    thickness = jig.plate_thickness_mm
    solid = _box(bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y, 0.0, thickness)
    for receptacle in jig.receptacles:
        solid -= _cylinder(
            receptacle.x, receptacle.y, receptacle.drill_diameter_mm, -0.5, thickness + 0.5
        )
    for pin in jig.alignment_pins:
        solid -= _cylinder(pin.x, pin.y, pin.diameter_mm, -0.5, thickness + 0.5)
    return solid


def build_pcb(models: MechanicalModels) -> Any:
    """Simplified PCB slab from the board outline and thickness."""
    pcb: PcbModel = models.pcb
    bounds = pcb.bounds
    return _box(bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y, 0.0, pcb.thickness_mm)


BUILDERS = {
    "plate": build_plate,
    "case": build_case,
    "jig": build_jig,
    "pcb": build_pcb,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def build_and_export(
    models: MechanicalModels,
    *,
    targets: list[str],
    formats: list[str],
    output_dir: Path,
) -> list[dict[str, Any]]:
    """Build the requested solids and write ``formats`` artifacts under ``output_dir``."""
    build123d = _require_build123d()
    output_dir.mkdir(parents=True, exist_ok=True)
    descriptors: list[dict[str, Any]] = []
    for target in targets:
        builder = BUILDERS.get(target)
        if builder is None:
            raise ValueError(f"unknown cad target {target!r}")
        solid = builder(models)
        for fmt in formats:
            path = output_dir / f"{target}.{fmt}"
            if fmt == "step":
                build123d.export_step(solid, str(path))
            elif fmt == "stl":
                build123d.export_stl(solid, str(path))
            else:
                raise ValueError(f"unknown export format {fmt!r}")
            descriptors.append(
                {
                    "target": target,
                    "kind": fmt,
                    "path": path,
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
    return descriptors


__all__ = [
    "BUILDERS",
    "CadUnavailableError",
    "build123d_available",
    "build_and_export",
    "build_case",
    "build_jig",
    "build_pcb",
    "build_plate",
]
