from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


def _find_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "examples" / "atomc-pad" / "system_ir.json").is_file():
            return parent
    raise RuntimeError("could not locate the atomc repository root from the test file")


REPO_ROOT = _find_repo_root()
EXAMPLE_IR = REPO_ROOT / "examples" / "atomc-pad" / "system_ir.json"
EXAMPLE_QMK = REPO_ROOT / "examples" / "atomc-pad" / "qmk"


@pytest.fixture
def example_ir() -> dict[str, Any]:
    return json.loads(EXAMPLE_IR.read_text(encoding="utf-8"))


@pytest.fixture
def example_qmk_root() -> Path:
    return EXAMPLE_QMK
