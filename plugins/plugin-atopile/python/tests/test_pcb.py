"""Pure mapping from :class:`BoardModel` to IR (no kiutils required for most cases)."""

from __future__ import annotations

from pathlib import Path

import pytest
from atomc_plugin_atopile.errors import BoardParseError
from atomc_plugin_atopile.pcb import (
    BoardModel,
    FootprintModel,
    PadModel,
    board_to_electrical,
    board_to_layout,
    load_board,
    net_id,
)

FIXTURE_BOARD = Path(__file__).parent / "fixtures" / "minimal.kicad_pcb"


def model() -> BoardModel:
    return BoardModel(
        path="board.kicad_pcb",
        thickness_mm=1.6,
        layers=2,
        outline=((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)),
        footprints=(
            FootprintModel(
                reference="TP1",
                lib_id="TestPoint:PACKAGE",
                value="VBUS",
                mpn=None,
                x=1.0,
                y=1.0,
                rotation_deg=0.0,
                side="bottom",
                pads=(PadModel(number="1", net_name="VBUS", x=1.0, y=1.0),),
            ),
            FootprintModel(
                reference="SW1",
                lib_id="Switch:SW_MX",
                value="SW_MX",
                mpn="Kailh",
                x=2.0,
                y=2.0,
                rotation_deg=90.0,
                side="top",
                pads=(
                    PadModel(number="1", net_name="ROW0", x=2.0, y=2.0),
                    PadModel(number="2", net_name="COL0", x=2.0, y=4.0),
                ),
            ),
        ),
    )


def test_net_id_sanitises_and_rejects_empty() -> None:
    assert net_id("VBUS") == "net:VBUS"
    assert net_id("1-5") == "net:1-5"
    assert net_id("A B") == "net:AB"
    assert net_id("") is None


def test_board_to_electrical_maps_pins_and_nets() -> None:
    result = board_to_electrical(model())
    by_id = {component["id"]: component for component in result["components"]}
    assert set(by_id) == {"comp:TP1", "comp:SW1"}
    assert by_id["comp:SW1"]["mpn"] == "Kailh"
    assert by_id["comp:SW1"]["pins"] == [
        {"number": "1", "net_ref": "net:ROW0"},
        {"number": "2", "net_ref": "net:COL0"},
    ]
    assert {net["id"] for net in result["nets"]} == {"net:VBUS", "net:ROW0", "net:COL0"}


def test_board_to_layout_filters_by_reference() -> None:
    updates = board_to_layout(
        model(),
        valid_component_ids={"comp:TP1"},
        valid_net_ids={"net:VBUS"},
    )
    assert {item["component_ref"] for item in updates["placements"]} == {"comp:TP1"}
    assert {item["id"] for item in updates["test_pads"]} == {"pad:TP1"}
    assert updates["outline"]["thickness_mm"] == 1.6


def test_board_to_layout_preserves_existing_entries() -> None:
    existing = {
        "placements": [
            {"component_ref": "comp:OTHER", "x": 0, "y": 0, "rotation_deg": 0, "side": "top"}
        ],
        "test_pads": [
            {
                "id": "pad:KEEP",
                "net_ref": "net:VBUS",
                "x": 0,
                "y": 0,
                "side": "bottom",
                "kind": "pogo",
            }
        ],
    }
    updates = board_to_layout(
        model(),
        valid_component_ids={"comp:TP1"},
        valid_net_ids={"net:VBUS"},
        existing=existing,
    )
    ids = {item["component_ref"] for item in updates["placements"]}
    assert ids == {"comp:OTHER", "comp:TP1"}
    pad_ids = {item["id"] for item in updates["test_pads"]}
    assert pad_ids == {"pad:KEEP", "pad:TP1"}


def test_board_to_layout_requires_outline() -> None:
    empty = BoardModel(path="b.kicad_pcb", thickness_mm=1.6, layers=2, outline=())
    with pytest.raises(BoardParseError):
        board_to_layout(empty, valid_component_ids=set(), valid_net_ids=set())


def test_load_board_real_fixture() -> None:
    pytest.importorskip("kiutils")
    board = load_board(FIXTURE_BOARD)
    assert [fp.reference for fp in board.footprints] == ["TP1", "TP2", "SW1"]
    tp1 = board.footprints[0]
    assert tp1.side == "bottom"
    assert tp1.pads[0].net_name == "VBUS"
    assert board.nets["net:VBUS"] == "VBUS"
    assert board.outline == ((0.0, 0.0), (30.0, 0.0), (30.0, 30.0), (0.0, 30.0))


def test_load_board_missing_file(tmp_path: Path) -> None:
    with pytest.raises(BoardParseError):
        load_board(tmp_path / "missing.kicad_pcb")
