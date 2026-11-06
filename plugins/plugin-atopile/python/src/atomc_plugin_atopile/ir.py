"""Small helpers for reading and writing IR nodes through a plugin context.

The daemon's ``PluginContext`` and the SDK's ``PluginHost`` disagree about the read API
(``ir_read`` returning ``{rev, value}`` vs ``ir_get`` returning a revision-tagged snapshot), so
these helpers normalise both. Writes always go through ``ir_transact`` with RFC 6902 operations
relative to the target node, matching ``docs/architecture/contracts/ir-schema.md`` §2.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any

from .context import PluginContext

__all__ = ["read_node", "read_value", "transact_node"]


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def read_value(ctx: PluginContext, path: str) -> Any | None:
    """Return the IR value at ``path`` or ``None`` when the node/pointer is absent."""
    getter = getattr(ctx, "ir_get", None)
    if getter is None:  # pragma: no cover - defensive
        return None
    try:
        raw = await _maybe_await(getter(path))
    except ValueError:
        # ``atomcd.ir_store.MissingNodeError`` subclasses ValueError; treat as absent.
        return None
    if hasattr(raw, "value") and hasattr(raw, "rev"):
        return raw.value
    if isinstance(raw, Mapping) and {"rev", "value"} <= set(raw):
        return raw["value"]
    return raw


async def read_node(ctx: PluginContext, path: str) -> tuple[int, Any | None]:
    """Return ``(node_rev, value)`` for a top-level node; ``(0, None)`` when absent."""
    reader = getattr(ctx, "ir_read", None)
    if reader is not None:
        try:
            data = await _maybe_await(reader(path))
        except ValueError:
            return 0, None
        if isinstance(data, Mapping) and {"rev", "value"} <= set(data):
            return int(data["rev"]), data["value"]
    value = await read_value(ctx, path)
    return 0, value


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


async def transact_node(
    ctx: PluginContext,
    path: str,
    updates: Mapping[str, Any],
) -> Any:
    """Write ``updates`` as node fields under ``path``.

    When the node is absent the whole node is created with a single relative ``add`` (a keyed
    patch cannot target a missing subtree). Otherwise each key is ``add``-ed relative to the
    node, which replaces an existing member or creates a new one.
    """
    rev, current = await read_node(ctx, path)
    if current is None:
        ops: list[dict[str, Any]] = [{"op": "add", "path": "", "value": dict(updates)}]
    else:
        ops = [
            {"op": "add", "path": f"/{_escape(key)}", "value": value}
            for key, value in updates.items()
        ]
    return await _maybe_await(ctx.ir_transact(path, rev, ops))
