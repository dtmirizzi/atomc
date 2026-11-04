"""Fixture round-trip and negative-fixture validation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from atomc_core_ir import RefIntegrityError, SystemIR
from pydantic import ValidationError

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"

VALID_FIXTURES = ["minimal.json", "atomc-pad.json"]
INVALID_FIXTURES = [
    "dangling_ref.json",
    "duplicate_id.json",
    "bad_unit_type.json",
    "extra_key.json",
    "keyboard_row_out_of_range.json",
]


@pytest.mark.parametrize("name", VALID_FIXTURES)
def test_roundtrip_is_byte_stable(name: str) -> None:
    path = FIXTURES_DIR / name
    original = path.read_text(encoding="utf-8")
    ir = SystemIR.load(path)
    assert ir.dump() == original
    assert SystemIR.load(ir.dump()).dump() == original


def test_load_accepts_path_str_and_bytes() -> None:
    path = FIXTURES_DIR / "atomc-pad.json"
    from_path = SystemIR.load(path)
    from_str = SystemIR.load(str(path))
    from_bytes = SystemIR.load(path.read_bytes())
    json_text = path.read_text(encoding="utf-8")
    from_json_text = SystemIR.load(json_text)
    assert from_path.dump() == from_str.dump() == from_bytes.dump() == from_json_text.dump()


@pytest.mark.parametrize("name", INVALID_FIXTURES)
def test_invalid_fixtures_rejected(name: str) -> None:
    path = FIXTURES_DIR / "invalid" / name
    with pytest.raises(ValueError, match=r"\S") as excinfo:
        SystemIR.load(path)
    assert str(excinfo.value)


def test_dangling_ref_message() -> None:
    with pytest.raises(RefIntegrityError) as excinfo:
        SystemIR.load(FIXTURES_DIR / "invalid" / "dangling_ref.json")
    assert "DOES_NOT_EXIST" in str(excinfo.value)


def test_duplicate_id_message() -> None:
    with pytest.raises(RefIntegrityError) as excinfo:
        SystemIR.load(FIXTURES_DIR / "invalid" / "duplicate_id.json")
    assert "duplicate id" in str(excinfo.value)


def test_extra_key_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        SystemIR.load(FIXTURES_DIR / "invalid" / "extra_key.json")


def test_bad_unit_type_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        SystemIR.load(FIXTURES_DIR / "invalid" / "bad_unit_type.json")


def test_minimal_fixture_has_only_meta() -> None:
    ir = SystemIR.load(FIXTURES_DIR / "minimal.json")
    assert ir.electrical is None
    assert ir.meta.project_id == "proj:minimal"
    payload = json.loads(ir.dump())
    assert sorted(payload) == ["ext", "meta", "schema_version"]
