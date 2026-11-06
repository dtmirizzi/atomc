"""The four gates: PASS/FAIL/SKIP against mutated IR fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from _helpers import FakeContext, build_ir
from atomc_plugin_atopile.gates import (
    MIN_TEST_PADS,
    check_assertions,
    check_no_unconnected,
    check_testpad_min_count,
    check_testpad_nets_covered,
)


def component(component_id: str, pins: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": component_id,
        "designator": component_id.split(":", 1)[1],
        "dnp": False,
        "attributes": {},
        "pins": pins,
    }


def electrical(
    components: list[dict[str, Any]],
    nets: list[str],
    assertions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "source": {"kind": "atopile", "entry": "main.ato:App"},
        "components": components,
        "nets": [{"id": net, "name": net.split(":", 1)[1]} for net in nets],
        "assertions": assertions or [],
        "erc": [],
    }


def layout(test_pads: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "outline": {"polygon": [[0.0, 0.0], [40.0, 0.0], [40.0, 40.0], [0.0, 40.0]]},
        "test_pads": test_pads,
    }


def keyboard(switch_ref: str, diode_ref: str) -> dict[str, Any]:
    return {
        "matrix": {
            "rows": 1,
            "cols": 1,
            "diode_direction": "COL2ROW",
            "row_pins": ["B12"],
            "col_pins": ["A0"],
        },
        "keys": [
            {
                "id": "key:K0_0",
                "row": 0,
                "col": 0,
                "switch_ref": switch_ref,
                "diode_ref": diode_ref,
            }
        ],
        "usb": {
            "vid": "0xFEED",
            "pid": "0x0001",
            "manufacturer": "atomc",
            "product": "pad",
        },
        "qmk": {"keyboard_path": "atomc/pad"},
    }


def pad(pad_id: str, net_ref: str) -> dict[str, Any]:
    return {"id": pad_id, "net_ref": net_ref, "x": 1.0, "y": 1.0, "side": "bottom", "kind": "pogo"}


def context(tmp_path: Path, **nodes: Any) -> FakeContext:
    return FakeContext(build_ir(**nodes), tmp_path / "artifacts")


# --- gate:erc.no_unconnected -------------------------------------------------


@pytest.mark.asyncio
async def test_no_unconnected_pass(tmp_path: Path) -> None:
    ctx = context(
        tmp_path,
        electrical=electrical(
            [
                component(
                    "comp:R1",
                    [{"number": "1", "net_ref": "net:A"}, {"number": "2", "net_ref": "net:B"}],
                ),
                component(
                    "comp:R2",
                    [{"number": "1", "net_ref": "net:A"}, {"number": "2", "net_ref": "net:B"}],
                ),
            ],
            ["net:A", "net:B"],
        ),
    )
    result = await check_no_unconnected(ctx)
    assert result.status == "PASS"


@pytest.mark.asyncio
async def test_no_unconnected_fail_on_single_pin_net(tmp_path: Path) -> None:
    ctx = context(
        tmp_path,
        electrical=electrical(
            [
                component(
                    "comp:R1",
                    [{"number": "1", "net_ref": "net:A"}, {"number": "2", "net_ref": "net:B"}],
                ),
                component(
                    "comp:R2",
                    [{"number": "1", "net_ref": "net:A"}, {"number": "2", "net_ref": "net:B"}],
                ),
                component("comp:R3", [{"number": "1", "net_ref": "net:ORPHAN"}]),
            ],
            ["net:A", "net:B", "net:ORPHAN"],
        ),
    )
    result = await check_no_unconnected(ctx)
    assert result.status == "FAIL"
    # Refs must resolve to document ids: the unconnected net, not pin-level refs
    # (pin detail rides in the evidence payload).
    assert result.refs == ["net:ORPHAN"]
    detail = result.evidence[0].model_dump()
    assert detail["kind"] == "json"
    assert detail["data"]["unconnected"][0]["pin_refs"] == ["comp:R3.1"]


@pytest.mark.asyncio
async def test_no_unconnected_skips_without_electrical(tmp_path: Path) -> None:
    result = await check_no_unconnected(context(tmp_path))
    assert result.status == "SKIP"


# --- gate:erc.assertions -----------------------------------------------------


@pytest.mark.asyncio
async def test_assertions_pass(tmp_path: Path) -> None:
    ctx = context(
        tmp_path,
        electrical=electrical([], [], [{"id": "assert:a", "expr": "x", "status": "pass"}]),
    )
    assert (await check_assertions(ctx)).status == "PASS"


@pytest.mark.asyncio
async def test_assertions_fail(tmp_path: Path) -> None:
    ctx = context(
        tmp_path,
        electrical=electrical(
            [],
            [],
            [
                {"id": "assert:a", "expr": "x", "status": "pass"},
                {"id": "assert:b", "expr": "y", "status": "fail"},
            ],
        ),
    )
    result = await check_assertions(ctx)
    assert result.status == "FAIL"
    assert result.refs == ["assert:b"]


@pytest.mark.asyncio
async def test_assertions_skip_on_unknown(tmp_path: Path) -> None:
    ctx = context(
        tmp_path,
        electrical=electrical([], [], [{"id": "assert:a", "expr": "x", "status": "unknown"}]),
    )
    assert (await check_assertions(ctx)).status == "SKIP"


@pytest.mark.asyncio
async def test_assertions_skip_when_none_recorded(tmp_path: Path) -> None:
    ctx = context(tmp_path, electrical=electrical([], []))
    assert (await check_assertions(ctx)).status == "SKIP"


# --- gate:layout.testpads.min_count -----------------------------------------


def nets_only(net_ids: list[str]) -> dict[str, Any]:
    return electrical([], net_ids)


@pytest.mark.asyncio
async def test_min_count_pass(tmp_path: Path) -> None:
    pads = [pad(f"pad:TP{i}", f"net:N{i}") for i in range(MIN_TEST_PADS)]
    ctx = context(
        tmp_path,
        electrical=nets_only([f"net:N{i}" for i in range(MIN_TEST_PADS)]),
        layout=layout(pads),
    )
    assert (await check_testpad_min_count(ctx)).status == "PASS"


@pytest.mark.asyncio
async def test_min_count_fail(tmp_path: Path) -> None:
    count = MIN_TEST_PADS - 1
    pads = [pad(f"pad:TP{i}", f"net:N{i}") for i in range(count)]
    ctx = context(
        tmp_path,
        electrical=nets_only([f"net:N{i}" for i in range(count)]),
        layout=layout(pads),
    )
    assert (await check_testpad_min_count(ctx)).status == "FAIL"


@pytest.mark.asyncio
async def test_min_count_skips_without_layout(tmp_path: Path) -> None:
    assert (await check_testpad_min_count(context(tmp_path))).status == "SKIP"


# --- gate:layout.testpads.nets_covered --------------------------------------


def matrix_electrical() -> dict[str, Any]:
    return electrical(
        [
            component(
                "comp:SW1",
                [{"number": "1", "net_ref": "net:ROW0"}, {"number": "2", "net_ref": "net:COL0"}],
            ),
            component(
                "comp:D1",
                [{"number": "1", "net_ref": "net:COL0"}, {"number": "2", "net_ref": "net:ROW0"}],
            ),
        ],
        ["net:ROW0", "net:COL0"],
    )


@pytest.mark.asyncio
async def test_nets_covered_pass(tmp_path: Path) -> None:
    ctx = context(
        tmp_path,
        electrical=matrix_electrical(),
        keyboard=keyboard("comp:SW1", "comp:D1"),
        layout=layout([pad("pad:TP_ROW0", "net:ROW0"), pad("pad:TP_COL0", "net:COL0")]),
    )
    assert (await check_testpad_nets_covered(ctx)).status == "PASS"


@pytest.mark.asyncio
async def test_nets_covered_fail(tmp_path: Path) -> None:
    ctx = context(
        tmp_path,
        electrical=matrix_electrical(),
        keyboard=keyboard("comp:SW1", "comp:D1"),
        layout=layout([pad("pad:TP_ROW0", "net:ROW0")]),
    )
    result = await check_testpad_nets_covered(ctx)
    assert result.status == "FAIL"
    assert result.refs == ["net:COL0"]


@pytest.mark.asyncio
async def test_nets_covered_skip_without_keyboard(tmp_path: Path) -> None:
    ctx = context(tmp_path, electrical=matrix_electrical(), layout=layout([]))
    assert (await check_testpad_nets_covered(ctx)).status == "SKIP"
