"""IR read helpers for optimizer gates and tools.

Reads normalize the daemon's ``ir_read``/``ir_get`` shapes without importing the daemon. Writes
always go through ``ir_transact`` so the daemon enforces the plugin's ``/sourcing`` scope.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any

__all__ = ["maybe_await", "read_node", "read_value"]


async def maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def read_value(ctx: Any, path: str) -> Any | None:
    """Return the IR value at ``path`` or ``None`` when absent."""
    getter = getattr(ctx, "ir_get", None)
    if getter is not None:
        try:
            raw = await maybe_await(getter(path))
        except ValueError:
            raw = None
        if raw is not None:
            if hasattr(raw, "value") and hasattr(raw, "rev"):
                return raw.value
            if isinstance(raw, Mapping) and {"rev", "value"} <= set(raw):
                return raw["value"]
            return raw
    reader = getattr(ctx, "ir_read", None)
    if reader is not None:
        try:
            data = await maybe_await(reader(path))
        except ValueError:
            return None
        if isinstance(data, Mapping) and {"rev", "value"} <= set(data):
            return data["value"]
        if hasattr(data, "value"):
            return data.value
        return data
    return None


async def read_node(ctx: Any, path: str) -> tuple[int, Any | None]:
    """Return ``(rev, value)`` for a node; ``(0, None)`` when absent."""
    reader = getattr(ctx, "ir_read", None)
    if reader is not None:
        try:
            data = await maybe_await(reader(path))
        except ValueError:
            return 0, None
        if isinstance(data, Mapping) and {"rev", "value"} <= set(data):
            return int(data["rev"]), data["value"]
        if hasattr(data, "rev") and hasattr(data, "value"):
            return int(data.rev), data.value
    value = await read_value(ctx, path)
    rev = 0
    if isinstance(value, Mapping):
        meta = value.get("_meta")
        if isinstance(meta, Mapping) and isinstance(meta.get("rev"), int):
            rev = int(meta["rev"])
    return rev, value
