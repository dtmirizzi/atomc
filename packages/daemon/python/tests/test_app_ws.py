"""WebSocket JSON-RPC: auth, envelope handling, IR methods, events and lifecycle."""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from atomcd.app import Services
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

ELECTRICAL_NODE: dict[str, Any] = {
    "_meta": {"rev": 0, "lock": None},
    "source": {"kind": "atopile", "entry": "main.ato:App"},
    "components": [],
    "nets": [],
    "assertions": [],
    "erc": [],
}


def _send(ws: Any, method: str, params: dict[str, Any] | None = None, req_id: int = 1) -> None:
    ws.send_text(
        json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}})
    )


def _recv(ws: Any) -> dict[str, Any]:
    """Receive the next JSON-RPC *response*, skipping event notifications."""
    while True:
        message = ws.receive_json()
        if message.get("method") == "event":
            continue
        return cast("dict[str, Any]", message)


def _call(
    ws: Any, method: str, params: dict[str, Any] | None = None, req_id: int = 1
) -> dict[str, Any]:
    _send(ws, method, params, req_id)
    return _recv(ws)


def test_missing_token_closes_1008(client: TestClient) -> None:
    with client.websocket_connect("/rpc") as ws, pytest.raises(WebSocketDisconnect) as exc_info:
        ws.receive_text()
    assert exc_info.value.code == 1008


def test_wrong_token_closes_1008(client: TestClient) -> None:
    with (
        client.websocket_connect("/rpc", headers={"Authorization": "Bearer nope"}) as ws,
        pytest.raises(WebSocketDisconnect) as exc_info,
    ):
        ws.receive_text()
    assert exc_info.value.code == 1008


def test_ir_get_root(client: TestClient, auth_headers: dict[str, str]) -> None:
    with client.websocket_connect("/rpc", headers=auth_headers) as ws:
        response = _call(ws, "ir.get", {})
    assert response["id"] == 1
    assert response["result"]["rev"] == 0
    assert response["result"]["value"]["schema_version"] == "0.1.0"


def test_ir_transact_then_get(
    client: TestClient, services: Services, auth_headers: dict[str, str]
) -> None:
    with client.websocket_connect("/rpc", headers=auth_headers) as ws:
        response = _call(
            ws,
            "ir.transact",
            {
                "path": "/electrical",
                "base_rev": 0,
                "ops": [{"op": "add", "path": "", "value": ELECTRICAL_NODE}],
            },
        )
        assert response["result"]["new_rev"] == 1
        assert response["result"]["changed_paths"] == ["/electrical"]
        fetched = _call(ws, "ir.get", {"path": "/electrical"}, req_id=2)
    assert fetched["result"]["rev"] == 1
    assert fetched["result"]["value"]["source"]["entry"] == "main.ato:App"
    assert services.store.rev == 1


def test_ir_transact_stale_conflict(client: TestClient, auth_headers: dict[str, str]) -> None:
    with client.websocket_connect("/rpc", headers=auth_headers) as ws:
        _call(
            ws,
            "ir.transact",
            {
                "path": "/electrical",
                "base_rev": 0,
                "ops": [{"op": "add", "path": "", "value": ELECTRICAL_NODE}],
            },
        )
        conflict = _call(
            ws,
            "ir.transact",
            {
                "path": "/electrical",
                "base_rev": 0,
                "ops": [{"op": "add", "path": "", "value": ELECTRICAL_NODE}],
            },
            req_id=2,
        )
    assert conflict["error"]["code"] == -32010
    assert conflict["error"]["data"] == {"current_rev": 1, "expected_rev": 0}


def test_ir_lock_conflict(client: TestClient, auth_headers: dict[str, str]) -> None:
    with client.websocket_connect("/rpc", headers=auth_headers) as ws:
        _call(
            ws,
            "ir.transact",
            {
                "path": "/electrical",
                "base_rev": 0,
                "ops": [{"op": "add", "path": "", "value": ELECTRICAL_NODE}],
            },
        )
        locked = _call(
            ws,
            "ir.lock",
            {"node": "/electrical", "holder": "agent:a", "ttl_s": 60},
            req_id=2,
        )
        assert "expires_at" in locked["result"]
        denied = _call(
            ws,
            "ir.transact",
            {
                "path": "/electrical",
                "base_rev": 1,
                "holder": "agent:b",
                "ops": [{"op": "replace", "path": "/source/entry", "value": "x.ato:App"}],
            },
            req_id=3,
        )
        assert denied["error"]["code"] == -32011
        assert denied["error"]["data"]["holder"] == "agent:a"
        released = _call(ws, "ir.unlock", {"node": "/electrical", "holder": "agent:a"}, req_id=4)
    assert released["result"] == {"released": True}


def test_missing_node_returns_invalid_params(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    with client.websocket_connect("/rpc", headers=auth_headers) as ws:
        response = _call(ws, "ir.get", {"path": "/mechanical"})
    assert response["error"]["code"] == -32602


def test_method_not_found(client: TestClient, auth_headers: dict[str, str]) -> None:
    with client.websocket_connect("/rpc", headers=auth_headers) as ws:
        response = _call(ws, "does.not.exist", {})
    assert response["error"]["code"] == -32601
    assert response["error"]["data"] == {"method": "does.not.exist"}


def test_invalid_params(client: TestClient, auth_headers: dict[str, str]) -> None:
    with client.websocket_connect("/rpc", headers=auth_headers) as ws:
        response = _call(ws, "ir.transact", {"path": "/electrical"})
    assert response["error"]["code"] == -32602
    assert response["error"]["data"]["errors"]


def test_parse_error(client: TestClient, auth_headers: dict[str, str]) -> None:
    with client.websocket_connect("/rpc", headers=auth_headers) as ws:
        ws.send_text("{not json")
        response = ws.receive_json()
    assert response["error"]["code"] == -32700
    assert response["id"] is None


def test_batch_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    with client.websocket_connect("/rpc", headers=auth_headers) as ws:
        ws.send_text(json.dumps([{"jsonrpc": "2.0", "id": 1, "method": "ir.get"}]))
        response = ws.receive_json()
    assert response["error"]["code"] == -32600


def test_invalid_envelope(client: TestClient, auth_headers: dict[str, str]) -> None:
    with client.websocket_connect("/rpc", headers=auth_headers) as ws:
        ws.send_text(json.dumps({"id": 1, "method": "ir.get"}))
        response = ws.receive_json()
    assert response["error"]["code"] == -32600


def test_notification_gets_no_response(client: TestClient, auth_headers: dict[str, str]) -> None:
    with client.websocket_connect("/rpc", headers=auth_headers) as ws:
        ws.send_text(json.dumps({"jsonrpc": "2.0", "method": "daemon.status"}))
        # A following request proves the notification was processed without a reply.
        response = _call(ws, "ir.get", {}, req_id=9)
    assert response["id"] == 9


def test_events_subscribe_and_publish(
    client: TestClient, services: Services, auth_headers: dict[str, str]
) -> None:
    with client.websocket_connect("/rpc", headers=auth_headers) as ws:
        response = _call(ws, "events.subscribe", {"topics": ["ir.changed"]})
        subscription = response["result"]["subscription"]
        services.events.publish("ir.changed", {"rev": 3, "changed_paths": ["/electrical"]})
        event = ws.receive_json()
        assert event["method"] == "event"
        assert event["params"]["topic"] == "ir.changed"
        assert event["params"]["data"]["rev"] == 3
        unsub = _call(ws, "events.unsubscribe", {"subscription": subscription}, req_id=2)
        assert unsub["result"] == {"unsubscribed": True}


def test_daemon_status(client: TestClient, auth_headers: dict[str, str]) -> None:
    with client.websocket_connect("/rpc", headers=auth_headers) as ws:
        response = _call(ws, "daemon.status", {})
    result = response["result"]
    assert result["pid"] == 12345
    assert result["version"] == "0.0.1"
    assert result["project_root"]


def test_daemon_shutdown_sets_event(
    client: TestClient, services: Services, auth_headers: dict[str, str]
) -> None:
    with client.websocket_connect("/rpc", headers=auth_headers) as ws:
        response = _call(ws, "daemon.shutdown", {})
    assert response["result"] == {"shutting_down": True}
    assert services.shutdown_event.is_set()
