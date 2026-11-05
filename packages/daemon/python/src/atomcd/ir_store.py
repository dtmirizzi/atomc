"""In-memory ``SystemIR`` store with canonical, crash-safe disk persistence.

Owns ``system_ir.json`` for a project:

* loads/creates the document,
* reads subtrees by RFC 6901 pointer and reports node revisions,
* applies ``core-ir`` transactions (optimistic revision + subtree locks),
* persists via temp-file + fsync + atomic replace, never writing after a failed
  validation, conflict or lock,
* serialises all mutations behind one narrow :class:`asyncio.Lock`.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atomc_core_ir import (
    ConflictError,
    LockedError,
    PatchError,
    RefIntegrityError,
    SystemIR,
    TxResult,
)
from atomc_core_ir import acquire_lock as core_acquire_lock
from atomc_core_ir import apply_patch as core_apply_patch
from atomc_core_ir import release_lock as core_release_lock
from pydantic import ValidationError

from .common import atomic_write_text

IR_FILENAME = "system_ir.json"


class MissingNodeError(ValueError):
    """The requested pointer targets a domain node that is absent from the document."""


def _pointer_parts(path: str) -> list[str]:
    if path in ("", "/"):
        return []
    if not path.startswith("/"):
        raise ValueError(f"invalid JSON pointer {path!r}: must start with '/'")
    return [seg.replace("~1", "/").replace("~0", "~") for seg in path[1:].split("/")]


def _resolve(doc: Any, parts: list[str]) -> Any:
    cur = doc
    for part in parts:
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            if part not in cur:
                raise KeyError(part)
            cur = cur[part]
        else:  # pragma: no cover - defensive
            raise KeyError(part)
    return cur


class IRStore:
    """Owns one project's ``system_ir.json``."""

    def __init__(self, project_root: Path | str) -> None:
        self.project_root = Path(project_root).expanduser()
        self.path = self.project_root / IR_FILENAME
        self._ir: SystemIR | None = None
        self._write_lock = asyncio.Lock()

    # -- lifecycle ----------------------------------------------------------

    def load(self) -> SystemIR:
        """Load the document from disk, creating an empty one if absent."""
        if self.path.exists():
            ir = SystemIR.load(self.path)
        else:
            project_id = f"proj:{self.project_root.name or 'project'}"
            ir = SystemIR.empty(project_id, self.project_root.name or "project")
            self.project_root.mkdir(parents=True, exist_ok=True)
            atomic_write_text(self.path, ir.dump())
        self._ir = ir
        return ir

    @property
    def snapshot(self) -> SystemIR:
        """The current validated document (read-only by convention)."""
        if self._ir is None:
            raise RuntimeError("IRStore.load() has not been called")
        return self._ir

    @property
    def rev(self) -> int:
        return self.snapshot.meta.rev

    # -- reads --------------------------------------------------------------

    def node_rev(self, path: str) -> int:
        """Revision reported for ``path``: document rev at ``/``, node ``_meta.rev`` below."""
        parts = _pointer_parts(path)
        doc = self.snapshot.model_dump(mode="json", by_alias=True)
        if not parts:
            return self.snapshot.meta.rev
        node_name = parts[0]
        node = doc.get(node_name)
        if node is None:
            raise MissingNodeError(f"node /{node_name} is not present")
        if len(parts) == 1:
            return int(node.get("_meta", {}).get("rev", 0))
        # A descendant: the owning node's rev.
        return int(node.get("_meta", {}).get("rev", 0))

    def read(self, path: str = "/") -> tuple[int, Any]:
        """Return ``(rev, value)`` for a pointer. Raises ``MissingNodeError`` if absent."""
        parts = _pointer_parts(path)
        doc = self.snapshot.model_dump(mode="json", by_alias=True)
        rev = self.node_rev(path)
        try:
            value = _resolve(doc, parts) if parts else doc
        except (KeyError, IndexError) as exc:
            raise MissingNodeError(f"pointer {path!r} not found: {exc}") from exc
        return rev, value

    # -- mutations ----------------------------------------------------------

    async def transact(
        self,
        path: str,
        base_rev: int,
        ops: list[dict[str, Any]],
        holder: str | None = None,
    ) -> TxResult:
        """Apply a relative JSON Patch transaction and persist the result.

        Raises ``ConflictError``, ``LockedError``, ``PatchError``, ``ValidationError`` or
        ``RefIntegrityError``. On any failure the stored document is untouched.
        """
        async with self._write_lock:
            ir = self.snapshot
            new_ir, result = core_apply_patch(ir, path, base_rev, ops, holder=holder)
            atomic_write_text(self.path, new_ir.dump())
            self._ir = new_ir
            return result

    async def lock(
        self,
        node: str,
        holder: str,
        ttl_s: int,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> str:
        """Acquire an advisory subtree lock. Returns the RFC 3339 expiry."""
        async with self._write_lock:
            ir = self.snapshot
            new_ir = core_acquire_lock(ir, node, holder, ttl_s, reason=reason, now=now)
            atomic_write_text(self.path, new_ir.dump())
            self._ir = new_ir
            lock = new_ir.model_dump(mode="json", by_alias=True)[node.strip("/").split("/")[0]][
                "_meta"
            ]["lock"]
            return str(lock["expires_at"])

    async def unlock(self, node: str, holder: str, now: datetime | None = None) -> bool:
        """Release a lock. Returns True if a lock was present before the call."""
        async with self._write_lock:
            ir = self.snapshot
            had = self._lock_present(node)
            new_ir = core_release_lock(ir, node, holder, now=now)
            if had:
                atomic_write_text(self.path, new_ir.dump())
                self._ir = new_ir
            return had

    def _lock_present(self, node: str) -> bool:
        name = node.strip("/").split("/")[0]
        node_obj = self.snapshot.model_dump(mode="json", by_alias=True).get(name)
        if node_obj is None:
            return False
        return node_obj.get("_meta", {}).get("lock") is not None

    # -- convenience --------------------------------------------------------

    def utcnow(self) -> datetime:
        return datetime.now(UTC)


__all__ = [
    "IR_FILENAME",
    "ConflictError",
    "IRStore",
    "LockedError",
    "MissingNodeError",
    "PatchError",
    "RefIntegrityError",
    "ValidationError",
]
