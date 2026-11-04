"""JSON Schema export for the unified system IR.

Usage::

    python -m atomc_core_ir.schema > packages/core-ir/schema/system_ir.schema.json
    python -m atomc_core_ir.schema --check   # exit 1 if the committed file has drifted
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .document import SCHEMA_VERSION, export_json_schema

DEFAULT_SCHEMA_PATH = Path("packages/core-ir/schema/system_ir.schema.json")


def canonical_schema() -> str:
    """Deterministic serialisation of the schema (sorted keys, 2-space indent, newline)."""
    return json.dumps(export_json_schema(), sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in args
    args = [a for a in args if a != "--check"]
    path = Path(args[0]) if args else DEFAULT_SCHEMA_PATH
    current = canonical_schema()
    if check:
        if not path.exists():
            print(f"schema file missing: {path}", file=sys.stderr)
            return 1
        if path.read_text(encoding="utf-8") != current:
            print(
                f"schema drift detected: {path} is stale; "
                "regenerate with `python -m atomc_core_ir.schema`",
                file=sys.stderr,
            )
            return 1
        print(f"schema up to date: {path}")
        return 0
    sys.stdout.write(current)
    return 0


__all__ = ["SCHEMA_VERSION", "canonical_schema", "export_json_schema", "main"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
