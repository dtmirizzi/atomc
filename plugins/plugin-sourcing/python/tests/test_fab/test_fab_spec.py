"""PCB spec and budget derivation from the system IR."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from atomc_plugin_sourcing.fab.spec import (
    DEFAULT_FAB_BUDGET_MINOR,
    DEFAULT_PCB_SPEC,
    budget_for_ir,
    pcb_spec_for_ir,
)


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "examples" / "atomc-pad" / "system_ir.json"
        if candidate.is_file():
            return parent
    raise RuntimeError("could not locate repository root")


def pad_document() -> dict[str, Any]:
    return json.loads((_repo_root() / "examples" / "atomc-pad" / "system_ir.json").read_text())


def test_pad_spec_is_derived_from_layout_and_build_qty() -> None:
    spec, evidence = pcb_spec_for_ir(pad_document())
    assert spec.layers == 2
    assert spec.width_mm == 80.0
    assert spec.height_mm == 80.0
    assert spec.thickness_mm == 1.6
    assert spec.qty == 5
    assert spec.finish == "HASL"
    assert spec.color == "green"
    assert any("outline bbox" in line for line in evidence)
    assert any("build_qty" in line for line in evidence)
    assert any("documented defaults" in line for line in evidence)


def test_existing_fabrication_spec_wins() -> None:
    document = {
        "fabrication": {
            "pcb": {
                "layers": 4,
                "width_mm": 12.0,
                "height_mm": 34.0,
                "thickness_mm": 0.8,
                "finish": "ENIG",
                "color": "black",
                "qty": 3,
            }
        }
    }
    spec, evidence = pcb_spec_for_ir(document)
    assert spec.layers == 4
    assert spec.finish == "ENIG"
    assert evidence == ["pcb spec read from /fabrication/pcb"]


def test_missing_layout_falls_back_to_documented_default() -> None:
    spec, evidence = pcb_spec_for_ir({})
    assert spec == DEFAULT_PCB_SPEC
    assert any("/layout is absent" in line for line in evidence)


def test_degenerate_outline_falls_back_to_default_size() -> None:
    document = {"layout": {"layers": 2, "outline": {"polygon": [[0.0, 0.0], [1.0, 1.0]]}}}
    spec, evidence = pcb_spec_for_ir(document)
    assert spec.width_mm == DEFAULT_PCB_SPEC.width_mm
    assert spec.height_mm == DEFAULT_PCB_SPEC.height_mm
    assert any("degenerate" in line for line in evidence)


def test_budget_prefers_project_budget() -> None:
    document = {"sourcing": {"budget": {"per_unit_minor": 1500, "total_minor": 7500}}}
    budget, source = budget_for_ir(document)
    assert budget == 7500
    assert source == "project budget /sourcing/budget.total_minor"


def test_budget_falls_back_to_default_threshold() -> None:
    budget, source = budget_for_ir({})
    assert budget == DEFAULT_FAB_BUDGET_MINOR
    assert "default" in source


@pytest.mark.parametrize("document", [None, {}, {"sourcing": {"budget": {}}}])
def test_budget_defaults_are_always_returned(document: dict[str, Any] | None) -> None:
    budget, _source = budget_for_ir(document)
    assert budget == DEFAULT_FAB_BUDGET_MINOR
