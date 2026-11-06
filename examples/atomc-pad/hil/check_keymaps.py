#!/usr/bin/env python3
"""Lightweight QMK keymap syntax/keycode sanity check.

This is fixture-content validation, not a plugin test. It intentionally has no
third-party dependencies and no QMK requirement: CI can ignore it, and it can be
run manually on any machine. It checks:

* balanced (), [], {} after stripping C comments and string literals;
* every LAYOUT(...) argument is a recognized keycode/macro shape;
* layer enum names and #define macros used in LAYOUT() are declared locally.

It does NOT prove the firmware compiles. Use qmk compile for that.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ALLOWED_PATTERNS = [
    re.compile(r"^KC_[A-Z0-9_]+$"),
    re.compile(r"^QK_[A-Z0-9_]+$"),
    re.compile(r"^_______$"),
    re.compile(r"^KC_TRNS$"),
    re.compile(r"^LT\(\s*[A-Za-z_][A-Za-z0-9_]*\s*,\s*KC_[A-Z0-9_]+\s*\)$"),
    re.compile(r"^MO\(\s*[A-Za-z_][A-Za-z0-9_]*\s*\)$"),
    re.compile(r"^TG\(\s*[A-Za-z_][A-Za-z0-9_]*\s*\)$"),
    re.compile(r"^DF\(\s*[A-Za-z_][A-Za-z0-9_]*\s*\)$"),
    re.compile(r"^OSL\(\s*[A-Za-z_][A-Za-z0-9_]*\s*\)$"),
    re.compile(r"^LM\(\s*[A-Za-z_][A-Za-z0-9_]*\s*,\s*MOD_[A-Z0-9_]+\s*\)$"),
]


def strip_comments_and_strings(text: str) -> str:
    """Remove // and /* */ comments and string/char literals."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r'"(?:\\.|[^"\\])*"', '""', text)
    text = re.sub(r"'(?:\\.|[^'\\])*'", "''", text)
    return text


def check_balance(text: str) -> list[str]:
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[tuple[str, int]] = []
    errors: list[str] = []
    for i, ch in enumerate(text):
        if ch in "([{":
            stack.append((ch, i))
        elif ch in ")]}":
            if not stack or stack[-1][0] != pairs[ch]:
                line = text.count("\n", 0, i) + 1
                errors.append(f"unbalanced '{ch}' at line {line}")
                continue
            stack.pop()
    for ch, i in stack:
        line = text.count("\n", 0, i) + 1
        errors.append(f"unclosed '{ch}' at line {line}")
    return errors


def split_top_level_commas(content: str) -> list[str]:
    args: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(content):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            args.append(content[start:i].strip())
            start = i + 1
    tail = content[start:].strip()
    if tail:
        args.append(tail)
    return [a for a in args if a]


def declared_names(text: str) -> set[str]:
    names: set[str] = set()
    for match in re.finditer(r"enum\s+layer_names\s*\{(.*?)\};", text, flags=re.S):
        names.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", match.group(1)))
    for match in re.finditer(r"^#define\s+([A-Za-z_][A-Za-z0-9_]*)", text, flags=re.M):
        names.add(match.group(1))
    return names


def find_layout_calls(text: str) -> list[tuple[int, str]]:
    calls: list[tuple[int, str]] = []
    for match in re.finditer(r"\bLAYOUT\s*\(", text):
        start = match.end()
        depth = 1
        i = start
        while i < len(text) and depth:
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
            i += 1
        if depth != 0:
            calls.append((match.start(), text[start:]))
        else:
            calls.append((match.start(), text[start : i - 1]))
    return calls


def validate_file(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8")
    text = strip_comments_and_strings(raw)
    errors = check_balance(text)
    names = declared_names(text)

    calls = find_layout_calls(text)
    if not calls:
        errors.append("no LAYOUT(...) call found")

    for offset, content in calls:
        line = text.count("\n", 0, offset) + 1
        for arg in split_top_level_commas(content):
            if arg in names:
                continue
            if any(pattern.match(arg) for pattern in ALLOWED_PATTERNS):
                continue
            errors.append(f"unrecognized keycode/macro '{arg}' in LAYOUT at line {line}")

    return errors


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    example_dir = script_dir.parent
    example_name = example_dir.name
    keyboard_name = example_name.removeprefix("atomc-")
    keymaps_dir = example_dir / "qmk" / "keyboards" / "atomc" / keyboard_name / "keymaps"

    if not keymaps_dir.is_dir():
        print(f"SKIP: keymaps directory not found: {keymaps_dir}", file=sys.stderr)
        return 0

    files = sorted(keymaps_dir.rglob("keymap.c"))
    if not files:
        print(f"SKIP: no keymap.c files under {keymaps_dir}", file=sys.stderr)
        return 0

    failed = False
    for path in files:
        errors = validate_file(path)
        rel = path.relative_to(example_dir)
        if errors:
            failed = True
            print(f"FAIL {rel}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"PASS {rel}")

    print(f"\nChecked {len(files)} keymap.c file(s) under {keymaps_dir}.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
