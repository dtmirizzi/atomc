"""JSON-Patch transactions and subtree locks for ``SystemIR``.

Implements the transaction semantics of ``docs/architecture/contracts/ir-schema.md`` §2.
All helpers are pure: they return new ``SystemIR`` objects and never mutate their input.
RFC 6902 (JSON Patch) is implemented in-house so ``atomc-core-ir`` stays dependency-free
beyond Pydantic.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import Field

from .common import AtomcModel, format_rfc3339
from .document import SystemIR

__all__ = [
    "ConflictError",
    "LockedError",
    "PatchError",
    "TxResult",
    "acquire_lock",
    "apply_patch",
    "release_lock",
]


class ConflictError(ValueError):
    """The client's ``base_rev`` does not match the current node revision."""

    def __init__(self, current_rev: int, expected_rev: int | None = None) -> None:
        self.current_rev = current_rev
        self.expected_rev = expected_rev
        msg = f"revision conflict: current node rev is {current_rev}"
        if expected_rev is not None:
            msg += f", client based on {expected_rev}"
        super().__init__(msg)


class LockedError(ValueError):
    """The target subtree is locked by another holder whose lock has not expired."""

    def __init__(self, holder: str, expires_at: str | datetime) -> None:
        self.holder = holder
        self.expires_at = expires_at
        if isinstance(expires_at, datetime):
            expires_at = format_rfc3339(expires_at)
        super().__init__(f"node locked by {holder!r} until {expires_at}")


class PatchError(ValueError):
    """An RFC 6902 patch could not be applied (bad path/op/value)."""


class TxResult(AtomcModel):
    new_rev: int = Field(ge=0)
    changed_paths: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# RFC 6902 JSON Patch
# ---------------------------------------------------------------------------


def _pointer_parts(path: str) -> list[str]:
    if path in ("", "/"):
        return []
    if not path.startswith("/"):
        raise PatchError(f"invalid JSON pointer {path!r}: must start with '/'")
    return [seg.replace("~1", "/").replace("~0", "~") for seg in path[1:].split("/")]


def _index(seq: list[Any], token: str) -> int:
    if not token.isdigit():
        raise PatchError(f"invalid array index {token!r}")
    idx = int(token)
    if idx >= len(seq):
        raise PatchError(f"array index {idx} out of range (len={len(seq)})")
    return idx


def _resolve(doc: Any, parts: list[str]) -> Any:
    cur = doc
    for part in parts:
        if isinstance(cur, list):
            cur = cur[_index(cur, part)]
        elif isinstance(cur, dict):
            if part not in cur:
                raise PatchError(f"path segment {part!r} not found")
            cur = cur[part]
        else:
            raise PatchError(f"cannot descend into {type(cur).__name__} at {part!r}")
    return cur


def _parent(doc: Any, parts: list[str]) -> tuple[Any, str]:
    if not parts:
        raise PatchError("operation requires a non-empty path")
    return _resolve(doc, parts[:-1]), parts[-1]


def _insert(parent: Any, token: str, value: Any) -> None:
    if isinstance(parent, list):
        if token == "-":
            parent.append(value)
            return
        if not token.isdigit():
            raise PatchError(f"invalid array index {token!r}")
        idx = int(token)
        if idx > len(parent):
            raise PatchError(f"array index {idx} out of range for insert")
        parent.insert(idx, value)
    elif isinstance(parent, dict):
        parent[token] = value
    else:
        raise PatchError(f"cannot insert into {type(parent).__name__}")


def _assign(parent: Any, token: str, value: Any) -> None:
    if isinstance(parent, list):
        parent[_index(parent, token)] = value
    elif isinstance(parent, dict):
        if token not in parent:
            raise PatchError(f"cannot replace missing member {token!r}")
        parent[token] = value
    else:
        raise PatchError(f"cannot assign into {type(parent).__name__}")


def _delete(parent: Any, token: str) -> Any:
    if isinstance(parent, list):
        return parent.pop(_index(parent, token))
    if isinstance(parent, dict):
        if token not in parent:
            raise PatchError(f"cannot remove missing member {token!r}")
        return parent.pop(token)
    raise PatchError(f"cannot remove from {type(parent).__name__}")


def _apply_ops(sub: Any, ops: list[dict[str, Any]]) -> Any:
    result = copy.deepcopy(sub)
    for op in ops:
        if not isinstance(op, dict) or "op" not in op:
            raise PatchError(f"invalid patch operation: {op!r}")
        kind = op["op"]
        parts = _pointer_parts(op.get("path", ""))
        if kind in ("add", "replace"):
            if "value" not in op:
                raise PatchError(f"operation {kind!r} requires a 'value'")
            value = copy.deepcopy(op["value"])
            if not parts:
                result = value
            elif kind == "add":
                parent, token = _parent(result, parts)
                _insert(parent, token, value)
            else:
                parent, token = _parent(result, parts)
                _assign(parent, token, value)
        elif kind == "remove":
            parent, token = _parent(result, parts)
            _delete(parent, token)
        elif kind == "move":
            from_parts = _pointer_parts(op.get("from", ""))
            parent, token = _parent(result, from_parts)
            value = _delete(parent, token)
            if not parts:
                result = value
            else:
                dest_parent, dest_token = _parent(result, parts)
                _insert(dest_parent, dest_token, value)
        elif kind == "copy":
            from_parts = _pointer_parts(op.get("from", ""))
            value = copy.deepcopy(_resolve(result, from_parts))
            if not parts:
                result = value
            else:
                dest_parent, dest_token = _parent(result, parts)
                _insert(dest_parent, dest_token, value)
        elif kind == "test":
            actual = _resolve(result, parts) if parts else result
            if actual != op.get("value"):
                raise PatchError(f"test failed at {op.get('path')!r}: {actual!r}")
        else:
            raise PatchError(f"unsupported patch op {kind!r}")
    return result


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _lock_active(lock: dict[str, Any], now: datetime) -> bool:
    return _parse_ts(lock["expires_at"]) > now


def _node_name(node: str) -> str:
    stripped = node.strip("/")
    if not stripped:
        raise ValueError("node name must not be empty")
    return stripped.split("/")[0]


def apply_patch(
    ir: SystemIR,
    path: str,
    base_rev: int,
    ops: list[dict[str, Any]],
    holder: str | None = None,
    now: datetime | None = None,
) -> tuple[SystemIR, TxResult]:
    """Apply an RFC 6902 patch relative to ``path`` with optimistic concurrency control.

    Raises ``ConflictError`` on a stale ``base_rev``, ``LockedError`` when another holder
    owns an unexpired lock, ``PatchError`` for malformed patches and Pydantic
    ``ValidationError``/``RefIntegrityError`` when the result is invalid. On any failure the
    input document is unchanged.
    """
    if now is None:
        now = datetime.now(UTC)
    doc = ir.model_dump(mode="json", by_alias=True)
    parts = _pointer_parts(path)
    node_name = parts[0] if parts else None

    if node_name is None:
        current_rev = doc["meta"]["rev"]
        _check_lock(doc, holder, now)  # nothing to check, kept for symmetry
    elif node_name == "meta":
        current_rev = doc["meta"]["rev"]
    elif node_name in SystemIR.DOMAIN_NODES:
        node = doc.get(node_name)
        if node is None:
            current_rev = 0
        else:
            current_rev = node.get("_meta", {}).get("rev", 0)
            lock = node.get("_meta", {}).get("lock")
            if lock is not None and _lock_active(lock, now) and lock.get("holder") != holder:
                raise LockedError(lock["holder"], lock["expires_at"])
    else:
        raise PatchError(f"path {path!r} does not target a top-level IR node")

    if current_rev != base_rev:
        raise ConflictError(current_rev, base_rev)

    subtree = _resolve(doc, parts) if parts else doc
    new_subtree = _apply_ops(subtree, ops)
    if parts:
        parent, token = _parent(doc, parts)
        if isinstance(parent, list):
            parent[_index(parent, token)] = new_subtree
        else:
            parent[token] = new_subtree
    else:
        doc = new_subtree

    new_rev = ir.meta.rev + 1
    doc["meta"]["rev"] = new_rev
    doc["meta"]["modified_at"] = format_rfc3339(now)

    if node_name in SystemIR.DOMAIN_NODES and doc.get(node_name) is not None:
        node = doc[node_name]
        if not isinstance(node, dict):
            raise PatchError(f"node {node_name!r} must be an object")
        meta = node.setdefault("_meta", {"rev": 0, "lock": None})
        meta["rev"] = new_rev

    result = SystemIR.model_validate(doc)
    result.validate_refs()

    base = path.rstrip("/")
    changed = []
    for op in ops:
        op_path = op.get("path", "")
        changed.append(base + op_path if base else op_path)
    return result, TxResult(new_rev=new_rev, changed_paths=changed)


def _check_lock(doc: dict[str, Any], holder: str | None, now: datetime) -> None:
    """Whole-document patches are not lockable; present for API symmetry."""
    del doc, holder, now


def acquire_lock(
    ir: SystemIR,
    node: str,
    holder: str,
    ttl_s: int,
    reason: str | None = None,
    now: datetime | None = None,
) -> SystemIR:
    """Take an advisory lock on a top-level domain node. Pure; does not bump ``rev``."""
    if now is None:
        now = datetime.now(UTC)
    name = _node_name(node)
    if name not in SystemIR.DOMAIN_NODES:
        raise ValueError(f"{name!r} is not a lockable top-level IR node")
    doc = ir.model_dump(mode="json", by_alias=True)
    target = doc.get(name)
    if target is None:
        raise ValueError(f"cannot lock missing node {name!r}")
    meta = target.setdefault("_meta", {"rev": 0, "lock": None})
    lock = meta.get("lock")
    if lock is not None and lock.get("holder") != holder and _lock_active(lock, now):
        raise LockedError(lock["holder"], lock["expires_at"])
    meta["lock"] = {
        "holder": holder,
        "acquired_at": format_rfc3339(now),
        "expires_at": format_rfc3339(now + timedelta(seconds=ttl_s)),
        "reason": reason,
    }
    result = SystemIR.model_validate(doc)
    result.validate_refs()
    return result


def release_lock(
    ir: SystemIR,
    node: str,
    holder: str,
    now: datetime | None = None,
) -> SystemIR:
    """Release a lock held by ``holder``. No-op when already unlocked."""
    if now is None:
        now = datetime.now(UTC)
    name = _node_name(node)
    if name not in SystemIR.DOMAIN_NODES:
        raise ValueError(f"{name!r} is not a lockable top-level IR node")
    doc = ir.model_dump(mode="json", by_alias=True)
    target = doc.get(name)
    if target is None:
        raise ValueError(f"cannot unlock missing node {name!r}")
    meta = target.setdefault("_meta", {"rev": 0, "lock": None})
    lock = meta.get("lock")
    if lock is None:
        return ir
    if lock.get("holder") != holder and _lock_active(lock, now):
        raise LockedError(lock["holder"], lock["expires_at"])
    meta["lock"] = None
    result = SystemIR.model_validate(doc)
    result.validate_refs()
    return result
