from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from atomc_plugin_qmk.derivation import (
    DerivationError,
    derive,
    derive_keyboard_json,
    derive_keymap_c,
    keycode_for_index,
    materialize,
)


def test_keyboard_json_byte_matches_fixture(
    example_ir: dict[str, Any], example_qmk_root: Path
) -> None:
    derived = derive(example_ir)
    expected = (example_qmk_root / "keyboards" / "atomc" / "pad" / "keyboard.json").read_text(
        encoding="utf-8"
    )
    assert derived.keyboard_json == expected


def test_keymap_byte_matches_fixture(example_ir: dict[str, Any], example_qmk_root: Path) -> None:
    derived = derive(example_ir)
    expected = (
        example_qmk_root / "keyboards" / "atomc" / "pad" / "keymaps" / "default" / "keymap.c"
    ).read_text(encoding="utf-8")
    assert derived.keymap_c == expected


def test_derived_file_layout(example_ir: dict[str, Any]) -> None:
    derived = derive(example_ir)
    assert set(derived.files) == {
        "keyboards/atomc/pad/keyboard.json",
        "keyboards/atomc/pad/keymaps/default/keymap.c",
    }
    assert derived.keyboard_path == "atomc/pad"


def test_missing_keyboard_raises() -> None:
    with pytest.raises(DerivationError, match="no /keyboard"):
        derive({"meta": {"name": "empty"}})


def test_pin_count_mismatch_raises(example_ir: dict[str, Any]) -> None:
    ir = copy.deepcopy(example_ir)
    ir["keyboard"]["matrix"]["row_pins"] = ["B12", "B13"]
    with pytest.raises(DerivationError, match="row_pins length"):
        derive(ir)


def test_invalid_keyboard_path_rejected(example_ir: dict[str, Any]) -> None:
    ir = copy.deepcopy(example_ir)
    ir["keyboard"]["qmk"]["keyboard_path"] = "../evil"
    with pytest.raises(DerivationError, match="keyboard_path"):
        derive(ir)


def test_layout_geometry_includes_non_default_dimensions(example_ir: dict[str, Any]) -> None:
    ir = copy.deepcopy(example_ir)
    key = ir["keyboard"]["keys"][0]
    key["w_u"] = 2.0
    key["h_u"] = 1.5
    key["rotation_deg"] = 15.0
    generated = derive_keyboard_json(ir)
    entry = generated["layouts"]["LAYOUT"]["layout"][0]
    assert entry["matrix"] == [0, 0]
    assert entry["x"] == 0
    assert entry["y"] == 0
    assert entry["w"] == 2.0
    assert entry["h"] == 1.5
    assert entry["r"] == 15.0


def test_keycode_sequence() -> None:
    assert keycode_for_index(0) == "KC_1"
    assert keycode_for_index(8) == "KC_9"
    assert keycode_for_index(9) == "KC_0"
    assert keycode_for_index(10) == "KC_A"
    assert keycode_for_index(35) == "KC_Z"
    assert keycode_for_index(36) == "KC_F1"
    assert keycode_for_index(59) == "KC_F24"
    with pytest.raises(DerivationError):
        keycode_for_index(60)


def test_materialize_writes_files(tmp_path: Path, example_ir: dict[str, Any]) -> None:
    derived = derive(example_ir)
    written = materialize(derived, tmp_path)
    assert set(written) == set(derived.files)
    for relative, path in written.items():
        assert path.is_file()
        assert path.read_text(encoding="utf-8") == derived.files[relative]
        assert path.read_bytes().endswith(b"\n")


def test_keyboard_json_is_valid_json(example_ir: dict[str, Any]) -> None:
    derived = derive(example_ir)
    parsed = json.loads(derived.keyboard_json)
    assert parsed["keyboard_name"] == "atomc-pad"
    assert parsed["matrix_pins"] == {
        "rows": ["B12", "B13", "B14"],
        "cols": ["A0", "A1", "A2"],
    }
    assert parsed["diode_direction"] == "COL2ROW"
    assert len(parsed["layouts"]["LAYOUT"]["layout"]) == 9


def test_keymap_has_single_base_layer(example_ir: dict[str, Any]) -> None:
    text = derive_keymap_c(example_ir)
    assert "[0] = LAYOUT(" in text
    assert text.count("KC_") == 9
    assert "[1]" not in text
