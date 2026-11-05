"""Arity-tolerant handler invocation (sync/async, 0/1/2 positional args)."""

from __future__ import annotations

import asyncio
from typing import Any

from atomcd.plugins.invoke import invoke

CTX = object()
PAYLOAD = {"q": "x"}


def test_sync_one_arg_gets_ctx() -> None:
    seen: list[Any] = []

    def handler(ctx: Any) -> str:
        seen.append(ctx)
        return "ok"

    assert asyncio.run(invoke(handler, CTX)) == "ok"
    assert seen == [CTX]


def test_sync_two_args_gets_ctx_and_payload() -> None:
    def handler(ctx: Any, payload: Any) -> Any:
        return (ctx, payload)

    assert asyncio.run(invoke(handler, CTX, PAYLOAD)) == (CTX, PAYLOAD)


def test_one_arg_with_payload_gets_payload_only() -> None:
    def handler(payload: Any) -> Any:
        return payload

    assert asyncio.run(invoke(handler, CTX, PAYLOAD)) == PAYLOAD


def test_zero_arg_handler() -> None:
    def handler() -> str:
        return "none"

    assert asyncio.run(invoke(handler, CTX)) == "none"
    assert asyncio.run(invoke(handler, CTX, PAYLOAD)) == "none"


async def test_async_handler_is_awaited() -> None:
    async def handler(ctx: Any) -> str:
        return "async"

    assert await invoke(handler, CTX) == "async"
