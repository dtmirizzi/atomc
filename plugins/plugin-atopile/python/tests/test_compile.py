"""``atopile.compile``: subprocess outcomes map to PASS/FAIL/UNAVAILABLE with real IR writes."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from _helpers import FakeContext, build_ir
from atomc_plugin_atopile.errors import BoardParseError, KiutilsUnavailableError
from atomc_plugin_atopile.pcb import BoardModel, FootprintModel, PadModel
from atomc_plugin_atopile.plugin import AtopilePlugin
from atomc_plugin_atopile.runner import CommandResult

FIXTURES = Path(__file__).parent / "fixtures"


@dataclass
class FakeRunner:
    result: CommandResult
    calls: list[tuple[tuple[str, ...], Path, int]] = field(default_factory=list)

    def run(self, argv: Any, *, cwd: Path, timeout_s: int) -> CommandResult:
        self.calls.append((tuple(argv), cwd, timeout_s))
        return self.result


def fake_board() -> BoardModel:
    return BoardModel(
        path="layout/default/default.kicad_pcb",
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
            FootprintModel(
                reference="D1",
                lib_id="Diode:SOD-123",
                value="1N4148W",
                mpn="1N4148W",
                x=10.0,
                y=25.0,
                rotation_deg=0.0,
                side="bottom",
                pads=(
                    PadModel(number="1", net_name="COL0", x=10.0, y=25.0),
                    PadModel(number="2", net_name="ROW0", x=10.0, y=27.0),
                ),
            ),
        ),
        nets={"net:VBUS": "VBUS", "net:ROW0": "ROW0", "net:COL0": "COL0"},
    )


def make_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    build = project / "build" / "builds" / "default"
    build.mkdir(parents=True)
    shutil.copy(FIXTURES / "sample.bom.json", build / "default.bom.json")
    shutil.copy(FIXTURES / "sample.variables.ato.json", build / "default.variables.ato.json")
    (project / "layout" / "default").mkdir(parents=True)
    shutil.copy(
        FIXTURES / "minimal.kicad_pcb", project / "layout" / "default" / "minimal.kicad_pcb"
    )
    return project


def make_plugin(
    *,
    result: CommandResult | None = None,
    board_loader: Any = None,
    which: Any = None,
) -> tuple[AtopilePlugin, FakeRunner]:
    runner = FakeRunner(result or CommandResult(returncode=0, stdout="ok"))
    plugin = AtopilePlugin(
        runner=runner,
        board_loader=board_loader or (lambda _path: fake_board()),
        which=which or (lambda _name: "/usr/local/bin/ato"),
    )
    return plugin, runner


def context(tmp_path: Path) -> FakeContext:
    return FakeContext(build_ir(), tmp_path / "artifacts")


@pytest.mark.asyncio
async def test_compile_success_writes_electrical(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    plugin, runner = make_plugin()
    ctx = context(tmp_path)
    result = await plugin.compile(ctx, {"project_dir": str(project)})

    assert result["status"] == "PASS"
    assert runner.calls
    assert runner.calls[0][0][1] == "build"
    assert ctx.transactions
    assert ctx.transactions[0][0] == "/electrical"
    electrical = ctx.ir.model_dump(mode="json", by_alias=True)["electrical"]
    assert electrical["source"]["kind"] == "atopile"
    component_ids = {component["id"] for component in electrical["components"]}
    assert {"comp:TP1", "comp:TP2", "comp:SW1", "comp:D1"} <= component_ids
    net_ids = {net["id"] for net in electrical["nets"]}
    assert net_ids == {"net:VBUS", "net:ROW0", "net:COL0"}
    sw1 = next(c for c in electrical["components"] if c["id"] == "comp:SW1")
    assert {pin["net_ref"] for pin in sw1["pins"]} == {"net:ROW0", "net:COL0"}


@pytest.mark.asyncio
async def test_compile_failure_traces_to_exit_code(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    plugin, _ = make_plugin(result=CommandResult(returncode=2, stderr="syntax error"))
    ctx = context(tmp_path)
    result = await plugin.compile(ctx, {"project_dir": str(project)})

    assert result["status"] == "FAIL"
    assert "2" in result["summary"]
    assert any("syntax error" in (item.get("message") or "") for item in result["evidence"])
    assert ctx.transactions == []
    assert ctx.ir.electrical is None


@pytest.mark.asyncio
async def test_compile_unavailable_without_ato(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    plugin, runner = make_plugin(which=lambda _name: None)
    ctx = context(tmp_path)
    result = await plugin.compile(ctx, {"project_dir": str(project)})

    assert result["status"] == "UNAVAILABLE"
    assert result["available"] is False
    assert runner.calls == []


@pytest.mark.asyncio
async def test_compile_missing_project_dir(tmp_path: Path) -> None:
    plugin, _ = make_plugin()
    result = await plugin.compile(context(tmp_path), {"project_dir": str(tmp_path / "nope")})
    assert result["status"] == "FAIL"


@pytest.mark.asyncio
async def test_compile_timeout_is_failure(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    plugin, _ = make_plugin(
        result=CommandResult(returncode=124, stderr="command timed out after 300s")
    )
    result = await plugin.compile(context(tmp_path), {"project_dir": str(project)})
    assert result["status"] == "FAIL"


@pytest.mark.asyncio
async def test_compile_survives_missing_kiutils(tmp_path: Path) -> None:
    project = make_project(tmp_path)

    def unavailable(_path: Path) -> BoardModel:
        raise KiutilsUnavailableError("kiutils is not installed")

    plugin, _ = make_plugin(board_loader=unavailable)
    ctx = context(tmp_path)
    result = await plugin.compile(ctx, {"project_dir": str(project)})

    assert result["status"] == "PASS"
    assert any("kiutils" in warning for warning in result["warnings"])
    electrical = ctx.ir.model_dump(mode="json", by_alias=True)["electrical"]
    assert electrical["nets"] == []
    assert any(c["id"] == "comp:SW1" for c in electrical["components"])


@pytest.mark.asyncio
async def test_compile_survives_board_parse_error(tmp_path: Path) -> None:
    project = make_project(tmp_path)

    def broken(_path: Path) -> BoardModel:
        raise BoardParseError("bad board")

    plugin, _ = make_plugin(board_loader=broken)
    result = await plugin.compile(context(tmp_path), {"project_dir": str(project)})
    assert result["status"] == "PASS"
    assert any("bad board" in warning for warning in result["warnings"])


@pytest.mark.asyncio
async def test_compile_fails_without_artifacts(tmp_path: Path) -> None:
    project = tmp_path / "empty"
    project.mkdir()
    plugin, _ = make_plugin()
    result = await plugin.compile(context(tmp_path), {"project_dir": str(project)})
    assert result["status"] == "FAIL"


@pytest.mark.asyncio
async def test_compile_merges_existing_electrical(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    existing = {
        "source": {"kind": "atopile", "entry": "main.ato:App"},
        "components": [
            {
                "id": "comp:U1",
                "designator": "U1",
                "dnp": False,
                "attributes": {},
                "pins": [],
            }
        ],
        "nets": [{"id": "net:3V3", "name": "3V3"}],
        "assertions": [],
    }
    ctx = FakeContext(build_ir(electrical=existing), tmp_path / "artifacts")
    plugin, _ = make_plugin()
    result = await plugin.compile(ctx, {"project_dir": str(project)})

    assert result["status"] == "PASS"
    document = ctx.ir.model_dump(mode="json", by_alias=True)["electrical"]
    component_ids = {c["id"] for c in document["components"]}
    net_ids = {n["id"] for n in document["nets"]}
    assert "comp:U1" in component_ids  # pre-existing reference preserved
    assert "net:3V3" in net_ids
