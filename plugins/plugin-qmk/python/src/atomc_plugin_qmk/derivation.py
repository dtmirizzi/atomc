"""Pure IR -> QMK derivation.

The functions here never touch the filesystem or the network unless :func:`materialize` is
called explicitly. They are the deterministic source for ``keyboard.json`` and the default
``keymap.c`` emitted under ``keyboards/<vendor>/<name>/``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "DerivationError",
    "DerivedQmk",
    "derive",
    "derive_keyboard_json",
    "derive_keymap_c",
    "keycode_for_index",
    "materialize",
]

_KEYBOARD_PATH_RE = re.compile(r"^[a-z0-9_-]+(?:/[a-z0-9_-]+)+$")
_DIGITS = [f"KC_{digit}" for digit in range(1, 10)] + ["KC_0"]
_LETTERS = [f"KC_{letter}" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
_FUNCTION_KEYS = [f"KC_F{index}" for index in range(1, 25)]
_KEYCODE_SEQUENCE = _DIGITS + _LETTERS + _FUNCTION_KEYS

# Metadata that QMK expects but the frozen IR keyboard node does not carry. These defaults are
# intentionally stable so a derivation is reproducible; projects can override them later.
DEFAULT_URL = "https://github.com/dtmirizzi/atomc"
DEFAULT_MAINTAINER = "dtmirizzi"
DEFAULT_FEATURES: dict[str, bool] = {
    "bootmagic": True,
    "extrakey": True,
    "mousekey": True,
    "nkro": True,
}


class DerivationError(ValueError):
    """The IR cannot be represented as a QMK keyboard definition."""


@dataclass(frozen=True)
class DerivedQmk:
    """Derived QMK sources for one keyboard, keyed by package-relative POSIX paths."""

    keyboard_path: str
    keyboard_json: str
    keymap_c: str
    keyboard_json_data: dict[str, Any]
    keymap: str = "default"

    @property
    def files(self) -> dict[str, str]:
        """Return ``{relative_path: content}`` for every derived file."""
        base = f"keyboards/{self.keyboard_path}"
        return {
            f"{base}/keyboard.json": self.keyboard_json,
            f"{base}/keymaps/{self.keymap}/keymap.c": self.keymap_c,
        }


def _as_dict(value: Any, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DerivationError(f"{what} must be a JSON object, got {type(value).__name__}")
    return value


def _keyboard(ir: Mapping[str, Any]) -> dict[str, Any]:
    keyboard = ir.get("keyboard")
    if not isinstance(keyboard, dict):
        raise DerivationError("IR has no /keyboard node; cannot derive QMK files")
    return keyboard


def _matrix(keyboard: Mapping[str, Any]) -> dict[str, Any]:
    matrix = _as_dict(keyboard.get("matrix"), "keyboard.matrix")
    rows = matrix.get("rows")
    cols = matrix.get("cols")
    if not isinstance(rows, int) or rows < 1:
        raise DerivationError("keyboard.matrix.rows must be a positive integer")
    if not isinstance(cols, int) or cols < 1:
        raise DerivationError("keyboard.matrix.cols must be a positive integer")
    row_pins = matrix.get("row_pins")
    col_pins = matrix.get("col_pins")
    if not isinstance(row_pins, list) or len(row_pins) != rows:
        raise DerivationError("keyboard.matrix.row_pins length must equal matrix.rows")
    if not isinstance(col_pins, list) or len(col_pins) != cols:
        raise DerivationError("keyboard.matrix.col_pins length must equal matrix.cols")
    return matrix


def _keys(keyboard: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = keyboard.get("keys", [])
    if not isinstance(raw, list):
        raise DerivationError("keyboard.keys must be a list")
    keys: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        key = _as_dict(item, f"keyboard.keys[{index}]")
        row = key.get("row")
        col = key.get("col")
        if not isinstance(row, int) or row < 0:
            raise DerivationError(f"keyboard.keys[{index}].row must be a non-negative integer")
        if not isinstance(col, int) or col < 0:
            raise DerivationError(f"keyboard.keys[{index}].col must be a non-negative integer")
        keys.append(key)
    return sorted(keys, key=lambda item: (int(item["row"]), int(item["col"])))


def _number(value: Any, field: str, default: float) -> int | float:
    if value is None:
        value = default
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise DerivationError(f"{field} must be a number")
    numeric = float(value)
    return int(numeric) if numeric.is_integer() else numeric


def _safe_keyboard_path(value: Any) -> str:
    if not isinstance(value, str) or not _KEYBOARD_PATH_RE.fullmatch(value):
        raise DerivationError(
            "keyboard.qmk.keyboard_path must be a relative 'vendor/name' path "
            "(lowercase letters, digits, '_' or '-')"
        )
    return value


def _layout_entry(key: Mapping[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "matrix": [int(key["row"]), int(key["col"])],
        "x": _number(key.get("x_u"), "key.x_u", 0.0),
        "y": _number(key.get("y_u"), "key.y_u", 0.0),
    }
    width = _number(key.get("w_u"), "key.w_u", 1.0)
    height = _number(key.get("h_u"), "key.h_u", 1.0)
    rotation = _number(key.get("rotation_deg"), "key.rotation_deg", 0.0)
    if width != 1:
        entry["w"] = width
    if height != 1:
        entry["h"] = height
    if rotation != 0:
        entry["r"] = rotation
    return entry


def keycode_for_index(index: int) -> str:
    """Return the positional keycode for a row-major matrix index.

    The first ten positions map to ``KC_1``..``KC_0``, then ``KC_A``..``KC_Z``, then
    ``KC_F1``..``KC_F24``. This keeps the example fixture's 3x3 keymap as ``KC_1``..``KC_9``.
    """
    if index < 0 or index >= len(_KEYCODE_SEQUENCE):
        raise DerivationError(
            f"matrix index {index} has no positional keycode; extend the keycode sequence"
        )
    return _KEYCODE_SEQUENCE[index]


def derive_keyboard_json(
    ir: Mapping[str, Any],
    *,
    url: str = DEFAULT_URL,
    maintainer: str = DEFAULT_MAINTAINER,
    features: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Build the QMK ``keyboard.json`` object from the IR keyboard node."""
    keyboard = _keyboard(ir)
    matrix = _matrix(keyboard)
    keys = _keys(keyboard)
    usb = _as_dict(keyboard.get("usb"), "keyboard.usb")
    qmk = _as_dict(keyboard.get("qmk"), "keyboard.qmk")
    meta = _as_dict(ir.get("meta", {}), "meta")

    board = qmk.get("board")
    if board is not None and not isinstance(board, str):
        raise DerivationError("keyboard.qmk.board must be a string when present")

    data: dict[str, Any] = {
        "keyboard_name": meta.get("name"),
        "manufacturer": usb.get("manufacturer"),
        "url": url,
        "maintainer": maintainer,
        "usb": {
            "vid": usb.get("vid"),
            "pid": usb.get("pid"),
            "device_version": usb.get("device_version", "1.0.0"),
        },
        "processor": qmk.get("processor"),
        "bootloader": qmk.get("bootloader", "stm32-dfu"),
    }
    if board is not None:
        data["board"] = board
    data["matrix_pins"] = {
        "rows": list(matrix["row_pins"]),
        "cols": list(matrix["col_pins"]),
    }
    data["diode_direction"] = matrix.get("diode_direction")
    data["features"] = dict(features or DEFAULT_FEATURES)
    data["layouts"] = {"LAYOUT": {"layout": [_layout_entry(key) for key in keys]}}
    return data


def derive_keymap_c(ir: Mapping[str, Any], *, keymap: str = "default") -> str:
    """Build the default ``keymap.c`` with one base layer derived from key positions."""
    keyboard = _keyboard(ir)
    matrix = _matrix(keyboard)
    keys = _keys(keyboard)
    if not keys:
        raise DerivationError("keyboard.keys is empty; cannot derive a keymap")
    meta = _as_dict(ir.get("meta", {}), "meta")
    created_at = str(meta.get("created_at", ""))
    year = created_at[:4] if created_at[:4].isdigit() else "2026"
    name = str(meta.get("name") or "keyboard")
    rows = int(matrix["rows"])
    cols = int(matrix["cols"])
    key_count = rows * cols
    kind = "macropad" if key_count == 9 else "keyboard"
    mapping = "digits 1-9" if key_count == 9 else "row-major keycodes"

    key_rows: list[str] = []
    for row in sorted({int(key["row"]) for key in keys}):
        row_keys = [key for key in keys if int(key["row"]) == row]
        codes = [keycode_for_index(row * cols + int(key["col"])) for key in row_keys]
        key_rows.append("        " + ", ".join(codes))
    layer = ",\n".join(key_rows)
    _ = keymap  # reserved for future non-default layers; the base layer is always index 0

    return (
        f"// Copyright {year} atomc contributors\n"
        "// SPDX-License-Identifier: GPL-2.0-or-later\n"
        "//\n"
        f"// Default keymap for the {name} {rows}x{cols} {kind}.\n"
        f"// Layout is a single BASE layer mapping the {rows}x{cols} matrix to {mapping}.\n"
        "\n"
        "#include QMK_KEYBOARD_H\n"
        "\n"
        "const uint16_t PROGMEM keymaps[][MATRIX_ROWS][MATRIX_COLS] = {\n"
        "    [0] = LAYOUT(\n"
        f"{layer}\n"
        "    ),\n"
        "};\n"
    )


def _scalar(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _inline_dict(value: Mapping[str, Any]) -> str:
    return (
        "{"
        + ", ".join(
            f"{json.dumps(str(key), ensure_ascii=False)}: {_inline_value(item)}"
            for key, item in value.items()
        )
        + "}"
    )


def _inline_value(value: Any) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(_inline_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return _inline_dict(value)
    return _scalar(value)


def _is_layout_entry(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and "matrix" in value
        and set(value).issubset({"matrix", "x", "y", "w", "h", "r"})
    )


def _is_flat_list(value: Any) -> bool:
    return isinstance(value, list) and all(
        item is None or isinstance(item, str | int | float | bool) for item in value
    )


def _format_keyboard_json(value: Any, indent: int = 0) -> str:
    """Format QMK keyboard.json in the committed fixture's compact style."""
    if value is None or isinstance(value, str | int | float | bool):
        return _scalar(value)
    if isinstance(value, dict):
        if _is_layout_entry(value):
            return _inline_dict(value)
        if not value:
            return "{}"
        lines = ["{"]
        items = list(value.items())
        for index, (key, item) in enumerate(items):
            comma = "," if index < len(items) - 1 else ""
            rendered = _format_keyboard_json(item, indent + 4)
            first, *rest = rendered.split("\n")
            lines.append(
                " " * (indent + 4) + json.dumps(str(key), ensure_ascii=False) + ": " + first
            )
            lines.extend(rest)
            if comma:
                lines[-1] += comma
        lines.append(" " * indent + "}")
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return "[]"
        if _is_flat_list(value):
            return "[" + ", ".join(_inline_value(item) for item in value) + "]"
        lines = ["["]
        for index, item in enumerate(value):
            comma = "," if index < len(value) - 1 else ""
            rendered = _format_keyboard_json(item, indent + 4)
            first, *rest = rendered.split("\n")
            lines.append(" " * (indent + 4) + first)
            lines.extend(rest)
            if comma:
                lines[-1] += comma
        lines.append(" " * indent + "]")
        return "\n".join(lines)
    raise DerivationError(f"cannot format JSON value of type {type(value).__name__}")


def derive(ir: Mapping[str, Any], *, keymap: str = "default") -> DerivedQmk:
    """Derive all QMK sources for the IR's keyboard node."""
    keyboard = _keyboard(ir)
    qmk = _as_dict(keyboard.get("qmk"), "keyboard.qmk")
    keyboard_path = _safe_keyboard_path(qmk.get("keyboard_path"))
    keyboard_json_data = derive_keyboard_json(ir)
    keyboard_json = _format_keyboard_json(keyboard_json_data) + "\n"
    keymap_c = derive_keymap_c(ir, keymap=keymap)
    return DerivedQmk(
        keyboard_path=keyboard_path,
        keyboard_json=keyboard_json,
        keymap_c=keymap_c,
        keyboard_json_data=keyboard_json_data,
        keymap=keymap,
    )


def materialize(derived: DerivedQmk, root: str | Path) -> dict[str, Path]:
    """Write derived files under ``root`` and return ``{relative_path: absolute_path}``."""
    base = Path(root)
    written: dict[str, Path] = {}
    for relative, content in derived.files.items():
        target = base / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        written[relative] = target
    return written
