"""Tolerant handler invocation shared by gates, tools, CLI and watch nodes.

The manifest contract fixes handler *names* but not their Python signatures. To stay compatible
with the plugin SDK while it is being built in parallel, the daemon adapts by arity:

* no payload: handler receives ``(ctx)`` when it accepts at least one positional argument;
* with payload: handler receives ``(ctx, payload)`` when it accepts two, ``(payload)`` when it
  accepts one, otherwise no arguments.

Both sync and async handlers are supported.
"""

from __future__ import annotations

import inspect
from typing import Any

_MISSING = object()


async def invoke(handler: Any, ctx: Any, payload: Any = _MISSING) -> Any:
    """Call ``handler`` with an arity-appropriate argument list and await if needed."""
    try:
        signature = inspect.signature(handler)
    except TypeError, ValueError:  # pragma: no cover - builtins/C callables
        signature = None

    if signature is None:
        args: tuple[Any, ...] = (ctx,) if payload is _MISSING else (ctx, payload)
    else:
        positional = [
            p
            for p in signature.parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        count = len(positional)
        if payload is _MISSING:
            args = (ctx,) if count >= 1 else ()
        elif count >= 2:
            args = (ctx, payload)
        elif count == 1:
            args = (payload,)
        else:
            args = ()

    result = handler(*args)
    if inspect.isawaitable(result):
        result = await result
    return result


__all__ = ["invoke"]
