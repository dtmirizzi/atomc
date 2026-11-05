"""JSON-RPC 2.0 error codes and the exception hierarchy used by ``atomcd``.

Implements the error mapping table in ``docs/architecture/contracts/rpc.md``.
"""

from __future__ import annotations

from typing import Any

# --- JSON-RPC / daemon error codes (frozen contract) -------------------------
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

REVISION_CONFLICT = -32010
LOCK_CONFLICT = -32011
VALIDATION_FAILED = -32012
DANGLING_REFERENCE = -32013
PLUGIN_FAILURE = -32020
DAG_FAILURE = -32030

MESSAGES: dict[int, str] = {
    PARSE_ERROR: "Parse error",
    INVALID_REQUEST: "Invalid request",
    METHOD_NOT_FOUND: "Method not found",
    INVALID_PARAMS: "Invalid params",
    INTERNAL_ERROR: "Internal error",
    REVISION_CONFLICT: "Optimistic revision conflict",
    LOCK_CONFLICT: "Subtree lock conflict",
    VALIDATION_FAILED: "IR validation failed",
    DANGLING_REFERENCE: "Dangling or duplicate IR reference",
    PLUGIN_FAILURE: "Plugin/tool failure",
    DAG_FAILURE: "DAG run failure",
}


class JsonRpcError(Exception):
    """An error that maps directly onto a JSON-RPC error object.

    ``data`` must never contain bearer tokens or other secrets; internal failures keep the
    full stack in the daemon log and expose only an opaque ``request_id``.
    """

    def __init__(self, code: int, message: str | None = None, data: Any = None) -> None:
        self.code = code
        self.message = message or MESSAGES.get(code, "Error")
        self.data = data
        super().__init__(f"[{code}] {self.message}")

    def to_object(self) -> dict[str, Any]:
        obj: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            obj["data"] = self.data
        return obj


class MethodNotFoundError(JsonRpcError):
    def __init__(self, method: str) -> None:
        super().__init__(METHOD_NOT_FOUND, data={"method": method})


class InvalidParamsError(JsonRpcError):
    def __init__(self, errors: list[dict[str, str]] | None = None) -> None:
        super().__init__(INVALID_PARAMS, data={"errors": errors or []})


class RevisionConflictError(JsonRpcError):
    def __init__(self, current_rev: int, expected_rev: int) -> None:
        super().__init__(
            REVISION_CONFLICT,
            data={"current_rev": current_rev, "expected_rev": expected_rev},
        )


class LockConflictError(JsonRpcError):
    def __init__(self, holder: str, expires_at: str) -> None:
        super().__init__(LOCK_CONFLICT, data={"holder": holder, "expires_at": expires_at})


class ValidationFailedError(JsonRpcError):
    def __init__(self, errors: list[dict[str, str]]) -> None:
        super().__init__(VALIDATION_FAILED, data={"errors": errors})


class DanglingReferenceError(JsonRpcError):
    def __init__(self, message: str, location: str | None = None) -> None:
        data: dict[str, Any] = {"message": message}
        if location is not None:
            data["location"] = location
        super().__init__(DANGLING_REFERENCE, data=data)


class PluginFailureError(JsonRpcError):
    def __init__(
        self,
        plugin: str,
        tool: str | None,
        retryable: bool,
        detail: str,
    ) -> None:
        super().__init__(
            PLUGIN_FAILURE,
            data={"plugin": plugin, "tool": tool, "retryable": retryable, "detail": detail},
        )


class DagRunFailureError(JsonRpcError):
    def __init__(self, run_id: str, node: str | None, detail: str) -> None:
        super().__init__(DAG_FAILURE, data={"run_id": run_id, "node": node, "detail": detail})


class InternalFailureError(JsonRpcError):
    """Opaque internal error: only the request id is exposed to the client."""

    def __init__(self, request_id: str) -> None:
        super().__init__(INTERNAL_ERROR, data={"request_id": request_id})


__all__ = [
    "DAG_FAILURE",
    "DANGLING_REFERENCE",
    "INTERNAL_ERROR",
    "INVALID_PARAMS",
    "INVALID_REQUEST",
    "LOCK_CONFLICT",
    "MESSAGES",
    "METHOD_NOT_FOUND",
    "PARSE_ERROR",
    "PLUGIN_FAILURE",
    "REVISION_CONFLICT",
    "VALIDATION_FAILED",
    "DagRunFailureError",
    "DanglingReferenceError",
    "InternalFailureError",
    "InvalidParamsError",
    "JsonRpcError",
    "LockConflictError",
    "MethodNotFoundError",
    "PluginFailureError",
    "RevisionConflictError",
    "ValidationFailedError",
]
