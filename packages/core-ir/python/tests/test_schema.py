"""Schema export and drift-detection tests."""

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from atomc_core_ir import export_json_schema
from atomc_core_ir.schema import canonical_schema, main

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "system_ir.schema.json"


def test_export_json_schema_uses_aliases() -> None:
    schema = export_json_schema()
    assert schema["title"] == "SystemIR"
    defs = schema["$defs"]
    assert "Electrical" in defs
    properties = defs["Electrical"]["properties"]
    assert "_meta" in properties  # JSON key uses the alias
    assert "meta_" not in properties


def test_committed_schema_is_up_to_date() -> None:
    assert canonical_schema() == SCHEMA_PATH.read_text(encoding="utf-8")


def test_check_passes_for_committed_schema() -> None:
    assert main(["--check", str(SCHEMA_PATH)]) == 0


def test_check_detects_drift(tmp_path: Path) -> None:
    drifted = tmp_path / "schema.json"
    drifted.write_text(canonical_schema() + " ", encoding="utf-8")
    assert main(["--check", str(drifted)]) == 1


def test_check_detects_missing_file(tmp_path: Path) -> None:
    assert main(["--check", str(tmp_path / "missing.json")]) == 1


def test_stdout_emits_canonical_schema() -> None:
    buffer = StringIO()
    with redirect_stdout(buffer):
        code = main([])
    assert code == 0
    assert buffer.getvalue() == canonical_schema()
