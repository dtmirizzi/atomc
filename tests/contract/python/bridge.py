#!/usr/bin/env python3
"""JSON-lines bridge between TypeScript and ``atomc_core_ir`` for contract tests.

The process reads one JSON request per stdin line and writes exactly one JSON
response per stdout line. It is deliberately stdlib-only (plus ``atomc-core-ir``)
so it can run under ``uv run --package atomc-core-ir python bridge.py``.

Requests::

    {"id": 1, "op": "validate", "ir": {<system_ir document>}}
    {"id": 2, "op": "patch", "ir": {...}, "path": "/electrical",
     "base_rev": 2, "ops": [<RFC 6902 ops>], "holder": "agent:test"}

Responses (one line, ``ok`` discriminates)::

    {"id": 1, "ok": true, "ir": {...}, "canonical": "<json string>"}
    {"id": 2, "ok": true, "ir": {...}, "canonical": "...",
     "new_rev": 3, "changed_paths": ["/electrical/assertions/0/status"]}
    {"id": 2, "ok": false, "error": {"type": "conflict", "message": "..."}}

The process exits non-zero when any request failed (or a stdin line was not
valid JSON), so a single-shot invocation still surfaces failures via exit code.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from atomc_core_ir import (
    ConflictError,
    LockedError,
    PatchError,
    RefIntegrityError,
    SystemIR,
    apply_patch,
)
from pydantic import ValidationError


def _error_type(exc: BaseException) -> str:
    if isinstance(exc, ConflictError):
        return "conflict"
    if isinstance(exc, LockedError):
        return "locked"
    if isinstance(exc, RefIntegrityError):
        return "ref_integrity"
    if isinstance(exc, PatchError):
        return "patch"
    if isinstance(exc, ValidationError):
        return "validation"
    return "error"


def _load_ir(raw: Any) -> SystemIR:
    # Round-trip through text so SystemIR.load never mistakes the payload for a path.
    return SystemIR.load(json.dumps(raw).encode("utf-8"))


def handle(request: dict[str, Any]) -> dict[str, Any]:
    op = request.get("op")
    if op == "validate":
        ir = _load_ir(request["ir"])
        return {"ir": json.loads(ir.dump()), "canonical": ir.dump()}
    if op == "patch":
        ir = _load_ir(request["ir"])
        new_ir, tx = apply_patch(
            ir,
            request["path"],
            int(request["base_rev"]),
            request["ops"],
            request.get("holder"),
        )
        return {
            "ir": json.loads(new_ir.dump()),
            "canonical": new_ir.dump(),
            "new_rev": tx.new_rev,
            "changed_paths": tx.changed_paths,
        }
    raise ValueError(f"unknown op {op!r}")


def main() -> int:
    had_error = False
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request_id: Any = None
        try:
            request = json.loads(line)
            request_id = request.get("id")
            response: dict[str, Any] = {"id": request_id, "ok": True, **handle(request)}
        except Exception as exc:
            had_error = True
            response = {
                "id": request_id,
                "ok": False,
                "error": {"type": _error_type(exc), "message": str(exc)},
            }
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()
    return 1 if had_error else 0


if __name__ == "__main__":
    sys.exit(main())
