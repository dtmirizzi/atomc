"""``atopile.import_pcb``: kiutils-backed layout import with referential-integrity filtering."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from _helpers import FakeContext, build_ir
from atomc_plugin_atopile.errors import BoardParseError, KiutilsUnavailableError
from atomc_plugin_atopile.pcb import BoardModel, FootprintModel, PadModel, load_board
from atomc_plugin_atopile.plugin import AtopilePlugin

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_BOARD = FIXTURES / "minimal.kicad_pcb"


def fake_board() -> BoardModel:
    return BoardModel(
        path=str(FIXTURE_BOARD),
        thickness_mm=1.6,
        layers=2,
        outline=((0.0, 0.0), (30.0, 0.0), (30.0, 30.0), (0.0, 30.0)),
        footprints=(
            FootprintModel(
                reference="TP1",
                lib_id="TestPoint:PACKAGE",
                value="VBUS",
                mpn=None,
                x=10.0,
                y=10.0,
                rotation_deg=0.0,
                side="bottom",
                pads=(PadModel(number="1", net_name="VBUS", x=10.0, y=10.0),),
            ),
            FootprintModel(
                reference="SW1",
                lib_id="Switch:SW_MX",
                value="SW_MX",
                mpn=None,
                x=10.0,
                y=20.0,
                rotation_deg=0.0,
                side="top",
                pads=(
                    PadModel(number="1", net_name="ROW0", x=5.0, y=20.0),
                    PadModel(number="2", net_name="COL0", x=15.0, y=20.0),
                ),
            ),
        ),
    )


def electrical() -> dict[str, Any]:
    return {
        "source": {"kind": "atopile", "entry": "main.ato:App"},
        "components": [
            {"id": "comp:TP1", "designator": "TP1", "dnp": False, "attributes": {}, "pins": []},
            {"id": "comp:SW1", "designator": "SW1", "dnp": False, "attributes": {}, "pins": []},
        ],
        "nets": [
            {"id": "net:VBUS", "name": "VBUS"},
            {"id": "net:ROW0", "name": "ROW0"},
            {"id": "net:COL0", "name": "COL0"},
        ],
        "assertions": [],
    }


def make_plugin(board_loader: Any) -> AtopilePlugin:
    return AtopilePlugin(board_loader=board_loader, which=lambda _name: None)


@pytest.mark.asyncio
async def test_import_pcb_writes_layout(tmp_path: Path) -> None:
    ctx = FakeContext(build_ir(electrical=electrical()), tmp_path / "artifacts")
    plugin = make_plugin(lambda _path: fake_board())
    result = await plugin.import_pcb(ctx, {"pcb_path": str(FIXTURE_BOARD)})

    assert result["status"] == "PASS"
    assert ctx.transactions
    assert ctx.transactions[0][0] == "/layout"
    layout = ctx.ir.model_dump(mode="json", by_alias=True)["layout"]
    assert layout["outline"]["polygon"] == [[0.0, 0.0], [30.0, 0.0], [30.0, 30.0], [0.0, 30.0]]
    assert {p["component_ref"] for p in layout["placements"]} == {"comp:TP1", "comp:SW1"}
    assert {p["id"] for p in layout["test_pads"]} == {"pad:TP1"}
    assert layout["test_pads"][0]["net_ref"] == "net:VBUS"


@pytest.mark.asyncio
async def test_import_pcb_filters_dangling_refs(tmp_path: Path) -> None:
    partial = electrical()
    del partial["components"][1]  # drop comp:SW1
    del partial["nets"][0]  # drop net:VBUS
    ctx = FakeContext(build_ir(electrical=partial), tmp_path / "artifacts")
    plugin = make_plugin(lambda _path: fake_board())
    result = await plugin.import_pcb(ctx, {"pcb_path": str(FIXTURE_BOARD)})

    assert result["status"] == "PASS"
    layout = ctx.ir.model_dump(mode="json", by_alias=True)["layout"]
    assert {p["component_ref"] for p in layout["placements"]} == {"comp:TP1"}
    assert layout["test_pads"] == []
    assert any("skipped" in warning for warning in result["warnings"])


@pytest.mark.asyncio
async def test_import_pcb_unavailable_without_kiutils(tmp_path: Path) -> None:
    def unavailable(_path: Path) -> BoardModel:
        raise KiutilsUnavailableError("kiutils is not installed")

    ctx = FakeContext(build_ir(electrical=electrical()), tmp_path / "artifacts")
    result = await make_plugin(unavailable).import_pcb(ctx, {"pcb_path": str(FIXTURE_BOARD)})
    assert result["status"] == "UNAVAILABLE"
    assert result["available"] is False


@pytest.mark.asyncio
async def test_import_pcb_failure_on_bad_board(tmp_path: Path) -> None:
    def broken(_path: Path) -> BoardModel:
        raise BoardParseError("cannot parse")

    ctx = FakeContext(build_ir(electrical=electrical()), tmp_path / "artifacts")
    result = await make_plugin(broken).import_pcb(ctx, {"pcb_path": str(FIXTURE_BOARD)})
    assert result["status"] == "FAIL"


@pytest.mark.asyncio
async def test_import_pcb_requires_path(tmp_path: Path) -> None:
    ctx = FakeContext(build_ir(), tmp_path / "artifacts")
    result = await make_plugin(lambda _path: fake_board()).import_pcb(ctx, {})
    assert result["status"] == "FAIL"


@pytest.mark.asyncio
async def test_import_pcb_real_kiutils_fixture(tmp_path: Path) -> None:
    pytest.importorskip("kiutils")
    board = load_board(FIXTURE_BOARD)
    assert board.thickness_mm == 1.6
    assert board.layers == 2
    assert board.outline == ((0.0, 0.0), (30.0, 0.0), (30.0, 30.0), (0.0, 30.0))

    ctx = FakeContext(build_ir(electrical=electrical()), tmp_path / "artifacts")
    result = await make_plugin(load_board).import_pcb(ctx, {"pcb_path": str(FIXTURE_BOARD)})
    assert result["status"] == "PASS"
    layout = ctx.ir.model_dump(mode="json", by_alias=True)["layout"]
    assert {p["component_ref"] for p in layout["placements"]} == {"comp:TP1", "comp:SW1"}
    assert {p["id"] for p in layout["test_pads"]} == {"pad:TP1"}
