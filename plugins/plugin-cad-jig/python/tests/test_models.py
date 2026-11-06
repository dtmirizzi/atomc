"""Golden checks for the pure model derivation against the atomc-pad fixture."""

from __future__ import annotations

from typing import Any

import pytest
from atomc_plugin_cad_jig.errors import ModelDerivationError
from atomc_plugin_cad_jig.models import (
    derive_case,
    derive_jig,
    derive_pcb,
    derive_plate,
)


def test_plate_derivation_matches_golden(atomc_pad_ir: dict[str, Any]) -> None:
    plate = derive_plate(atomc_pad_ir)
    assert len(plate.cutouts) == 9
    assert plate.bounds.min_x == pytest.approx(0.0)
    assert plate.bounds.max_x == pytest.approx(80.0)
    assert plate.cutout_mm == pytest.approx(14.0)
    assert plate.pitch_mm == pytest.approx(19.05)
    assert plate.thickness_mm == pytest.approx(1.5)
    assert plate.material == "PLA"
    centers = sorted((c.x, c.y) for c in plate.cutouts)
    assert centers[0] == pytest.approx((10.0, 10.0))
    assert (29.05, 29.05) in [(round(x, 4), round(y, 4)) for x, y in centers]
    assert {c.switch_ref for c in plate.cutouts} == {f"comp:SW{i}" for i in range(1, 10)}


def test_plate_missing_switch_placement_raises(atomc_pad_ir: dict[str, Any]) -> None:
    placements = atomc_pad_ir["layout"]["placements"]
    atomc_pad_ir["layout"]["placements"] = [
        p for p in placements if p["component_ref"] != "comp:SW5"
    ]
    with pytest.raises(ModelDerivationError) as excinfo:
        derive_plate(atomc_pad_ir)
    assert "comp:SW5" in str(excinfo.value)


def test_case_derivation_usb_cutout(atomc_pad_ir: dict[str, Any]) -> None:
    case = derive_case(atomc_pad_ir)
    assert case.connector_ref == "comp:J1"
    assert case.usb_cutout.edge == "left"
    assert case.usb_cutout.center_along_edge_mm == pytest.approx(40.0)
    assert case.usb_cutout.width_mm == pytest.approx(4.0)
    # 3 mm connector bbox height is floored to the USB-C opening default of 3.2 mm
    assert case.usb_cutout.height_mm == pytest.approx(3.2)
    assert case.usb_cutout.z_center_mm == pytest.approx(1.5)
    # connector centre (5, 40); nearest board edge is x=0, so the gap is 5 mm
    assert case.edge_gap_mm == pytest.approx(5.0)
    assert case.outer.min_x == pytest.approx(-2.4)
    assert case.inner.min_x == pytest.approx(-0.4)
    assert case.wall_mm == pytest.approx(2.0)


def test_jig_derivation_pogo_and_pins(atomc_pad_ir: dict[str, Any]) -> None:
    jig = derive_jig(atomc_pad_ir)
    assert len(jig.receptacles) == 15
    assert len(jig.alignment_pins) == 4
    assert jig.pogo_part == "P75-E2"
    assert jig.min_pitch_mm == pytest.approx(2.54)
    assert jig.plate_thickness_mm == pytest.approx(5.0)
    assert all(r.drill_diameter_mm == pytest.approx(2.0) for r in jig.receptacles)
    assert {p.hole_ref for p in jig.alignment_pins} == {"hole:H1", "hole:H2", "hole:H3", "hole:H4"}


def test_pcb_projection(atomc_pad_ir: dict[str, Any]) -> None:
    pcb = derive_pcb(atomc_pad_ir)
    assert len(pcb.outline) == 4
    assert pcb.bounds.width == pytest.approx(80.0)
    assert {c.component_ref for c in pcb.components} == {"comp:U1", "comp:J1"}
    assert pcb.keepouts == ()


def test_mounting_hole_outside_outline_raises(atomc_pad_ir: dict[str, Any]) -> None:
    atomc_pad_ir["layout"]["mounting_holes"][0]["x"] = -5.0
    with pytest.raises(ModelDerivationError):
        derive_jig(atomc_pad_ir)
