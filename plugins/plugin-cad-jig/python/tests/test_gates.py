"""PASS/FAIL paths for the five mechanical gates on the atomc-pad fixture."""

from __future__ import annotations

from typing import Any

from atomc_plugin_cad_jig.gates import (
    check_case_usb_cutout_aligned,
    check_enclosure_clearance,
    check_jig_no_collision,
    check_plate_switch_cutouts,
    check_pogo_spacing,
)
from atomc_plugin_cad_jig.models import derive_models


def test_all_gates_pass_on_fixture(atomc_pad_ir: dict[str, Any]) -> None:
    models = derive_models(atomc_pad_ir)
    assert check_plate_switch_cutouts(models)["status"] == "PASS"
    assert check_case_usb_cutout_aligned(models)["status"] == "PASS"
    assert check_pogo_spacing(models)["status"] == "PASS"
    assert check_jig_no_collision(models)["status"] == "PASS"
    assert check_enclosure_clearance(models)["status"] == "PASS"


def test_plate_gate_fails_on_wrong_cutout(atomc_pad_ir: dict[str, Any]) -> None:
    atomc_pad_ir["mechanical"]["plate"]["cutout_mm"] = 13.0
    result = check_plate_switch_cutouts(derive_models(atomc_pad_ir))
    assert result["status"] == "FAIL"
    assert "13.000" in result["summary"]
    assert result["refs"]


def test_plate_gate_fails_on_wrong_pitch(atomc_pad_ir: dict[str, Any]) -> None:
    for placement in atomc_pad_ir["layout"]["placements"]:
        if placement["component_ref"] == "comp:SW2":
            placement["x"] = placement["x"] + 1.0
    result = check_plate_switch_cutouts(derive_models(atomc_pad_ir))
    assert result["status"] == "FAIL"


def test_usb_gate_fails_when_connector_leaves_edge(atomc_pad_ir: dict[str, Any]) -> None:
    for placement in atomc_pad_ir["layout"]["placements"]:
        if placement["component_ref"] == "comp:J1":
            placement["x"] = 40.0
            placement["y"] = 40.0
    result = check_case_usb_cutout_aligned(derive_models(atomc_pad_ir))
    assert result["status"] == "FAIL"
    assert "board edge" in result["summary"]


def test_pogo_gate_fails_on_duplicate_pad(atomc_pad_ir: dict[str, Any]) -> None:
    pads = atomc_pad_ir["layout"]["test_pads"]
    pads[1]["x"] = pads[0]["x"]
    pads[1]["y"] = pads[0]["y"]
    result = check_pogo_spacing(derive_models(atomc_pad_ir))
    assert result["status"] == "FAIL"
    assert "0.000" in result["summary"]


def test_jig_gate_fails_when_pogo_hits_component(atomc_pad_ir: dict[str, Any]) -> None:
    for pad in atomc_pad_ir["layout"]["test_pads"]:
        if pad["id"] == "pad:TP_VBUS":
            pad["x"] = 40.0
            pad["y"] = 40.0
    result = check_jig_no_collision(derive_models(atomc_pad_ir))
    assert result["status"] == "FAIL"
    assert "comp:U1" in result["summary"]


def test_jig_gate_fails_when_pogo_off_board(atomc_pad_ir: dict[str, Any]) -> None:
    for pad in atomc_pad_ir["layout"]["test_pads"]:
        if pad["id"] == "pad:TP_VBUS":
            pad["y"] = 200.0
    result = check_jig_no_collision(derive_models(atomc_pad_ir))
    assert result["status"] == "FAIL"
    assert "off the board" in result["summary"]


def test_enclosure_gate_fails_on_thin_wall(atomc_pad_ir: dict[str, Any]) -> None:
    atomc_pad_ir["mechanical"]["enclosure"]["wall_mm"] = 0.4
    result = check_enclosure_clearance(derive_models(atomc_pad_ir))
    assert result["status"] == "FAIL"
    assert "wall thickness" in result["summary"]


def test_enclosure_gate_fails_when_component_escapes_cavity(atomc_pad_ir: dict[str, Any]) -> None:
    for bbox in atomc_pad_ir["mechanical"]["component_bboxes"]:
        if bbox["component_ref"] == "comp:U1":
            bbox["max"][0] = 400.0
    result = check_enclosure_clearance(derive_models(atomc_pad_ir))
    assert result["status"] == "FAIL"
    assert "comp:U1" in result["summary"]


def test_keepout_collision_fails(atomc_pad_ir: dict[str, Any]) -> None:
    atomc_pad_ir["layout"]["keepouts"] = [
        {"id": "keepout:1", "min": [5.0, 5.0, 0.0], "max": [7.0, 7.0, 0.0]}
    ]
    result = check_jig_no_collision(derive_models(atomc_pad_ir))
    assert result["status"] == "FAIL"
    assert "keepout" in result["summary"]
