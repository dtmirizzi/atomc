"""Golden tests for the JSON-RPC envelope layer, independent of the WebSocket transport.

These lock the wire shapes from ``docs/architecture/contracts/rpc.md``: exact response bodies,
error objects and notification envelopes, plus param validation.
"""

from __future__ import annotations

import json

import pytest
from atomcd.errors import (
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    InvalidParamsError,
    JsonRpcError,
    MethodNotFoundError,
    RevisionConflictError,
)
from atomcd.rpc import (
    RequestEnvelope,
    error_response,
    notification,
    parse_message,
    parse_params,
    result_response,
    validation_errors,
)
from pydantic import ValidationError


def test_result_response_golden() -> None:
    assert result_response(7, {"rev": 3, "value": {"schema_version": "0.1.0"}}) == {
        "jsonrpc": "2.0",
        "id": 7,
        "result": {"rev": 3, "value": {"schema_version": "0.1.0"}},
    }


def test_error_response_golden() -> None:
    assert error_response(7, RevisionConflictError(2, 1)) == {
        "jsonrpc": "2.0",
        "id": 7,
        "error": {
            "code": -32010,
            "message": "Optimistic revision conflict",
            "data": {"current_rev": 2, "expected_rev": 1},
        },
    }


def test_error_omits_data_when_none() -> None:
    assert error_response(None, JsonRpcError(PARSE_ERROR)) == {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": PARSE_ERROR, "message": "Parse error"},
    }


def test_notification_golden() -> None:
    assert notification("event", {"topic": "ir.changed", "data": {"rev": 1}}) == {
        "jsonrpc": "2.0",
        "method": "event",
        "params": {"topic": "ir.changed", "data": {"rev": 1}},
    }


def test_parse_valid_request() -> None:
    outcome = parse_message('{"jsonrpc":"2.0","id":1,"method":"ir.get","params":{}}')
    assert outcome.error is None
    assert outcome.request is not None
    assert outcome.request.id == 1
    assert outcome.is_notification is False


def test_parse_notification() -> None:
    outcome = parse_message('{"jsonrpc":"2.0","method":"daemon.status"}')
    assert outcome.request is not None
    assert outcome.request.id is None
    assert outcome.is_notification is True


def test_parse_invalid_json_is_parse_error() -> None:
    outcome = parse_message("{oops")
    assert outcome.error is not None
    assert outcome.error.code == PARSE_ERROR
    assert outcome.error.data["detail"]


def test_parse_batch_rejected() -> None:
    outcome = parse_message('[{"jsonrpc":"2.0","id":1,"method":"ir.get"}]')
    assert outcome.error is not None
    assert outcome.error.code == INVALID_REQUEST


def test_parse_non_object_rejected() -> None:
    outcome = parse_message('"hello"')
    assert outcome.error is not None
    assert outcome.error.code == INVALID_REQUEST


def test_parse_missing_jsonrpc_rejected() -> None:
    outcome = parse_message('{"id":1,"method":"ir.get"}')
    assert outcome.error is not None
    assert outcome.error.code == INVALID_REQUEST
    assert outcome.error.data["errors"]


def test_request_envelope_forbids_extra_keys() -> None:
    with pytest.raises(ValidationError) as exc_info:
        RequestEnvelope.model_validate({"jsonrpc": "2.0", "id": 1, "method": "x", "extra": True})
    assert validation_errors(exc_info.value)[0]["type"] == "extra_forbidden"


def test_parse_params_valid() -> None:
    params = parse_params("ir.transact", {"path": "/electrical", "base_rev": 0, "ops": []})
    assert params.path == "/electrical"
    assert params.base_rev == 0


def test_parse_params_defaults() -> None:
    params = parse_params("ir.get", None)
    assert params.path == "/"


def test_parse_params_rejects_array() -> None:
    with pytest.raises(InvalidParamsError) as exc_info:
        parse_params("ir.get", [1, 2])
    assert exc_info.value.code == -32602
    assert exc_info.value.data["errors"][0]["message"] == "params must be an object"


def test_parse_params_reports_field_errors() -> None:
    with pytest.raises(InvalidParamsError) as exc_info:
        parse_params("ir.transact", {"path": "/electrical"})
    paths = {e["path"] for e in exc_info.value.data["errors"]}
    assert "base_rev" in paths
    assert "ops" in paths


def test_method_not_found_error_shape() -> None:
    obj = MethodNotFoundError("nope").to_object()
    assert obj == {
        "code": METHOD_NOT_FOUND,
        "message": "Method not found",
        "data": {"method": "nope"},
    }


def test_jsonrpc_error_message_defaults_by_code() -> None:
    assert JsonRpcError(-32099).message == "Error"


def test_response_is_json_serialisable() -> None:
    payload = error_response(1, MethodNotFoundError("x"))
    assert json.loads(json.dumps(payload))["error"]["code"] == METHOD_NOT_FOUND
