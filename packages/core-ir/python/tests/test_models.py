"""Model-level validator tests (ids, units, keyboard, gates, timestamps)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from atomc_core_ir import (
    Artifact,
    Component,
    DocumentMeta,
    GateResult,
    Gates,
    Key,
    Keyboard,
    Matrix,
    Net,
    NodeMeta,
    Outline,
    Qmk,
    SystemIR,
    Usb,
    make_node_meta,
    validate_ir_id,
)
from atomc_core_ir.testing import minimal_system_ir
from pydantic import ValidationError


def _meta() -> dict[str, object]:
    return {"rev": 0, "lock": None}


def test_validate_ir_id_accepts_valid_and_rejects_invalid() -> None:
    assert validate_ir_id("comp:U1") == "comp:U1"
    assert validate_ir_id("gate:erc.no_unconnected") == "gate:erc.no_unconnected"
    with pytest.raises(ValueError, match="invalid IR id"):
        validate_ir_id("Bad")
    with pytest.raises(ValueError, match="invalid IR id"):
        validate_ir_id("no-colon")
    with pytest.raises(ValueError, match="invalid IR id"):
        validate_ir_id("1comp:U1")


def test_component_id_is_validated() -> None:
    with pytest.raises(ValidationError):
        Component(id="not-an-id", designator="U1")


def test_net_class_alias_roundtrips() -> None:
    net = Net(id="net:3V3", name="3V3", net_class="power")
    assert net.model_dump(by_alias=True)["class"] == "power"
    assert Net.model_validate({"id": "net:3V3", "name": "3V3", "class": "ground"}).net_class


def test_outline_requires_three_points() -> None:
    with pytest.raises(ValidationError):
        Outline(polygon=[[0.0, 0.0], [1.0, 1.0]])


def test_artifact_hash_is_validated() -> None:
    with pytest.raises(ValidationError):
        Artifact(
            id="art:x",
            kind="elf",
            path="x",
            sha256="deadbeef",
            bytes=1,
            produced_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_naive_timestamps_rejected() -> None:
    with pytest.raises(ValidationError):
        DocumentMeta(
            project_id="proj:x",
            name="x",
            created_at=datetime(2026, 1, 1),
            modified_at=datetime(2026, 1, 1),
            atomc_version="0.1.0",
        )


def _keyboard(rows: int = 2, cols: int = 2) -> Keyboard:
    return Keyboard(
        meta_=NodeMeta(rev=0),
        matrix=Matrix(
            rows=rows,
            cols=cols,
            diode_direction="COL2ROW",
            row_pins=[f"B{i}" for i in range(rows)],
            col_pins=[f"A{i}" for i in range(cols)],
        ),
        keys=[Key(id="key:K0_0", row=0, col=0)],
        usb=Usb(vid="0x1", pid="0x2", manufacturer="m", product="p"),
        qmk=Qmk(keyboard_path="atomc/pad"),
    )


def test_keyboard_pin_count_validation() -> None:
    with pytest.raises(ValidationError):
        Matrix(rows=2, cols=2, diode_direction="COL2ROW", row_pins=["B0"], col_pins=["A0", "A1"])
    with pytest.raises(ValidationError):
        Matrix(rows=2, cols=2, diode_direction="COL2ROW", row_pins=["B0", "B1"], col_pins=["A0"])


def test_keyboard_row_and_col_range() -> None:
    kb = _keyboard()
    assert kb.keys[0].row == 0
    with pytest.raises(ValidationError):
        Keyboard(
            meta_=NodeMeta(rev=0),
            matrix=Matrix(
                rows=2,
                cols=2,
                diode_direction="COL2ROW",
                row_pins=["B0", "B1"],
                col_pins=["A0", "A1"],
            ),
            keys=[Key(id="key:K9_9", row=9, col=9)],
            usb=Usb(vid="0x1", pid="0x2", manufacturer="m", product="p"),
            qmk=Qmk(keyboard_path="atomc/pad"),
        )


def test_keyboard_duplicate_positions_rejected() -> None:
    with pytest.raises(ValidationError):
        Keyboard(
            meta_=NodeMeta(rev=0),
            matrix=Matrix(
                rows=2,
                cols=2,
                diode_direction="COL2ROW",
                row_pins=["B0", "B1"],
                col_pins=["A0", "A1"],
            ),
            keys=[Key(id="key:K0_0", row=0, col=0), Key(id="key:K0_1", row=0, col=0)],
            usb=Usb(vid="0x1", pid="0x2", manufacturer="m", product="p"),
            qmk=Qmk(keyboard_path="atomc/pad"),
        )


def test_gates_result_key_must_match_id() -> None:
    result = GateResult(
        id="gate:bom.all_in_stock",
        status="PASS",
        plugin="plugin:sourcing@0.1.0",
        evaluated_at=datetime(2026, 1, 1, tzinfo=UTC),
        ir_rev=1,
    )
    assert Gates(meta_=NodeMeta(rev=0), results={"bom.all_in_stock": result})
    with pytest.raises(ValidationError):
        Gates(meta_=NodeMeta(rev=0), results={"wrong_key": result})


def test_schema_version_must_match() -> None:
    with pytest.raises(ValidationError):
        SystemIR(
            schema_version="9.9.9",
            meta=DocumentMeta(
                project_id="proj:x",
                name="x",
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                modified_at=datetime(2026, 1, 1, tzinfo=UTC),
                atomc_version="0.1.0",
            ),
        )


def test_empty_and_make_node_meta() -> None:
    ir = SystemIR.empty("proj:e", "empty")
    assert ir.meta.rev == 0
    assert ir.layout is None
    assert make_node_meta(4).rev == 4
    assert make_node_meta().lock is None


def test_minimal_system_ir_helper() -> None:
    ir = minimal_system_ir()
    assert ir.meta.name == "minimal"
