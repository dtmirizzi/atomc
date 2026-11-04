from __future__ import annotations

from pathlib import Path

import pytest

CORE_IR_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = CORE_IR_ROOT / "fixtures"
SCHEMA_PATH = CORE_IR_ROOT / "schema" / "system_ir.schema.json"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def schema_path() -> Path:
    return SCHEMA_PATH
