"""Small shared helpers: canonical atomic writes and UTC timestamps."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utcnow_iso() -> str:
    """RFC 3339 UTC timestamp with second precision (matches core-ir)."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def utcnow() -> datetime:
    return datetime.now(UTC)


def atomic_write_text(path: Path, text: str, *, mode: int = 0o644) -> None:
    """Write ``text`` to ``path`` atomically: temp file + fsync + ``os.replace``.

    The parent directory is created if needed and fsynced so the rename is durable.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
        dir_fd = os.open(str(path.parent), os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def atomic_write_json(path: Path, payload: Any, *, mode: int = 0o644) -> None:
    """Canonical JSON (sorted keys, 2-space indent, trailing newline) written atomically."""
    text = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    atomic_write_text(path, text, mode=mode)


__all__ = ["atomic_write_json", "atomic_write_text", "utcnow", "utcnow_iso"]
