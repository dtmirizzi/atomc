"""FastAPI application: HTTP health/schema endpoints and the authenticated JSON-RPC WebSocket.

The app is deliberately thin: it wires services together and owns the WebSocket lifecycle
(auth, per-connection dispatching, subscription draining, graceful shutdown). Method logic
lives in :mod:`atomcd.rpc`.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
from dataclasses import dataclass, field
from typing import Any

from atomc_core_ir import export_json_schema
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from . import VERSION
from .config import DaemonConfig
from .events import EventBus, Subscription
from .ir_store import IRStore
from .rpc import Dispatcher, dump, error_response, notification, parse_message
from .runtime import RuntimeState

WS_POLICY_VIOLATION = 1008


@dataclass
class Services:
    """Shared, process-wide daemon services."""

    config: DaemonConfig
    store: IRStore
    runtime_state: RuntimeState
    events: EventBus
    version: str = VERSION
    dag: Any = None
    gates: Any = None
    plugins: Any = None
    logger: Any = None
    shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)


def create_app(services: Services) -> FastAPI:
    """Build the FastAPI app for the given services."""
    app = FastAPI(
        title="atomcd",
        version=services.version,
        description="atomc daemon: system IR store, DAG scheduler, gate runner, JSON-RPC host",
    )
    app.state.services = services

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "version": services.version, "ir_rev": services.store.rev}

    @app.get("/schema")
    async def schema() -> dict[str, Any]:
        return export_json_schema()

    @app.websocket("/rpc")
    async def rpc_socket(websocket: WebSocket) -> None:
        await _handle_websocket(websocket, services)

    return app


def _authorized(websocket: WebSocket, token: str) -> bool:
    header = websocket.headers.get("authorization")
    if not header or not header.lower().startswith("bearer "):
        return False
    presented = header[7:].strip()
    return hmac.compare_digest(presented, token)


async def _handle_websocket(websocket: WebSocket, services: Services) -> None:
    """Authenticate, then serve one JSON-RPC connection until close/shutdown."""
    if not _authorized(websocket, services.config.effective_token):
        await websocket.accept()
        await websocket.close(code=WS_POLICY_VIOLATION)
        return

    await websocket.accept()
    send_lock = asyncio.Lock()
    drain_tasks: dict[str, asyncio.Task[None]] = {}

    async def send(payload: dict[str, Any]) -> None:
        async with send_lock:
            if websocket.client_state is WebSocketState.CONNECTED:
                await websocket.send_text(dump(payload))

    def register(subscription: Subscription) -> None:
        drain_tasks[subscription.id] = asyncio.create_task(_drain(subscription, send))

    def unregister(subscription_id: str) -> None:
        task = drain_tasks.pop(subscription_id, None)
        if task is not None:
            task.cancel()

    dispatcher = Dispatcher(
        store=services.store,
        config=services.config,
        runtime_state=services.runtime_state,
        events=services.events,
        version=services.version,
        dag=services.dag,
        gates=services.gates,
        plugins=services.plugins,
        on_shutdown=services.shutdown_event.set,
        logger=services.logger,
    )
    dispatcher.subscription_sink = register
    dispatcher.unsubscription_sink = unregister

    shutdown_requested = False
    try:
        while True:
            raw = await websocket.receive_text()
            outcome = parse_message(raw)
            if outcome.error is not None:
                await send(error_response(None, outcome.error))
                continue
            assert outcome.request is not None
            response = await dispatcher.dispatch(outcome.request)
            if outcome.is_notification:
                # Notifications get no response; still executed for side effects.
                continue
            await send(response)
            if (
                "error" not in response
                and outcome.request.method == "daemon.shutdown"
                and outcome.request.id is not None
            ):
                shutdown_requested = True
                break
    except WebSocketDisconnect:
        pass
    finally:
        for task in drain_tasks.values():
            task.cancel()
        for task in drain_tasks.values():
            with contextlib.suppress(asyncio.CancelledError):
                await task
        drain_tasks.clear()
        if shutdown_requested:
            services.shutdown_event.set()


async def _drain(subscription: Subscription, send: Any) -> None:
    """Forward one subscription's queued events to the socket as ``event`` notifications."""
    while True:
        event = await subscription.queue.get()
        body = notification("event", {"topic": event.topic, "data": event.data})
        try:
            await send(body)
        except WebSocketDisconnect, RuntimeError:
            return


__all__ = ["WS_POLICY_VIOLATION", "Services", "create_app"]
