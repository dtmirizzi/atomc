"""JSON-RPC 2.0 envelope parsing and the method dispatcher.

Implements ``docs/architecture/contracts/rpc.md``: single requests only (batch rejected with
``-32600``), exact id echo, notifications produce no response, and the frozen error mapping.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import errors
from .errors import InternalFailureError, InvalidParamsError, JsonRpcError, MethodNotFoundError
from .events import EventBus

JSONRPC_VERSION = "2.0"


class RequestEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jsonrpc: Literal["2.0"]
    id: int | str | None = None
    method: str
    params: dict[str, Any] | list[Any] | None = None


# --- param models ------------------------------------------------------------


class IrGetParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = "/"


class IrTransactParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    base_rev: int = Field(ge=0)
    ops: list[dict[str, Any]]
    holder: str | None = None


class IrLockParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node: str
    holder: str
    ttl_s: int = Field(gt=0)
    reason: str | None = None


class IrUnlockParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node: str
    holder: str


class DagRunParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    targets: list[str] | None = None
    force: bool = False


class GatesParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] | None = None


class ToolsListParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent: str | None = None


class ToolsCallParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plugin: str
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    holder: str | None = None


class EventsSubscribeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topics: list[str]


class EventsUnsubscribeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subscription: str


PARAM_MODELS: dict[str, type[BaseModel]] = {
    "ir.get": IrGetParams,
    "ir.transact": IrTransactParams,
    "ir.lock": IrLockParams,
    "ir.unlock": IrUnlockParams,
    "dag.run": DagRunParams,
    "gates.list": GatesParams,
    "gates.run": GatesParams,
    "tools.list": ToolsListParams,
    "tools.call": ToolsCallParams,
    "events.subscribe": EventsSubscribeParams,
    "events.unsubscribe": EventsUnsubscribeParams,
}


def parse_params(method: str, params: Any) -> Any:
    """Validate ``params`` against the method's model. Raises ``InvalidParamsError`` on failure.

    Methods with no declared params return an empty ``dict`` (params must still be absent or
    an object, never an array).
    """
    model = PARAM_MODELS.get(method)
    raw: Any = params if params is not None else {}
    if isinstance(raw, list):
        raise InvalidParamsError([{"path": "", "message": "params must be an object"}])
    if model is None:
        return raw
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        details = [
            {"path": "/".join(str(p) for p in err["loc"]), "message": err["msg"]}
            for err in exc.errors()
        ]
        raise InvalidParamsError(details) from exc


def validation_errors(exc: ValidationError) -> list[dict[str, str]]:
    """Turn a Pydantic error into ``{path, message, type}`` entries."""
    out: list[dict[str, str]] = []
    for err in exc.errors():
        out.append(
            {
                "path": "/".join(str(p) for p in err["loc"]),
                "message": err["msg"],
                "type": str(err["type"]),
            }
        )
    return out


def error_response(request_id: Any, error: JsonRpcError) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": error.to_object()}


def result_response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def notification(method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "method": method, "params": params}


def dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


@dataclass
class ParseOutcome:
    """Result of decoding one incoming WebSocket text frame."""

    request: RequestEnvelope | None = None
    error: JsonRpcError | None = None
    is_notification: bool = False


def parse_message(raw: str) -> ParseOutcome:
    """Decode a text frame into a request or a parse/invalid-request error."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return ParseOutcome(error=JsonRpcError(errors.PARSE_ERROR, data={"detail": str(exc)}))
    if isinstance(payload, list):
        return ParseOutcome(
            error=JsonRpcError(errors.INVALID_REQUEST, data={"detail": "batch not supported"})
        )
    if not isinstance(payload, dict):
        return ParseOutcome(
            error=JsonRpcError(errors.INVALID_REQUEST, data={"detail": "request must be object"})
        )
    try:
        envelope = RequestEnvelope.model_validate(payload)
    except ValidationError as exc:
        return ParseOutcome(
            error=JsonRpcError(errors.INVALID_REQUEST, data={"errors": validation_errors(exc)})
        )
    return ParseOutcome(request=envelope, is_notification=envelope.id is None)


class Dispatcher:
    """Dispatches validated JSON-RPC requests to services."""

    def __init__(
        self,
        *,
        store: Any,
        config: Any,
        runtime_state: Any,
        events: EventBus,
        version: str,
        dag: Any = None,
        gates: Any = None,
        plugins: Any = None,
        on_shutdown: Callable[[], Awaitable[None] | None] | None = None,
        logger: Any = None,
    ) -> None:
        self.store = store
        self.config = config
        self.runtime_state = runtime_state
        self.events = events
        self.version = version
        self.dag = dag
        self.gates = gates
        self.plugins = plugins
        self.on_shutdown = on_shutdown
        self.logger = logger
        self._request_counter = 0
        # Per-connection hooks installed by the WebSocket handler.
        self.subscription_sink: Callable[[Any], None] | None = None
        self.unsubscription_sink: Callable[[str], None] | None = None

    async def dispatch(self, request: RequestEnvelope) -> dict[str, Any]:
        """Handle one request and return its response object (caller echoes ``id``)."""
        self._request_counter += 1
        request_id = f"req-{self._request_counter}"
        try:
            params = parse_params(request.method, request.params)
            result = await self._call(request.method, params)
            return result_response(request.id, result)
        except JsonRpcError as exc:
            return error_response(request.id, exc)
        except (KeyError, ValueError) as exc:
            return error_response(
                request.id, InvalidParamsError([{"path": "", "message": str(exc)}])
            )
        except Exception:
            if self.logger is not None:
                self.logger.exception(
                    "rpc_internal_error", request_id=request_id, method=request.method
                )
            return error_response(request.id, InternalFailureError(request_id))

    async def _call(self, method: str, params: Any) -> Any:
        handler = getattr(self, f"_m_{method.replace('.', '_')}", None)
        if handler is None or method not in self._methods():
            raise MethodNotFoundError(method)
        return await handler(params)

    @staticmethod
    def _methods() -> set[str]:
        return {
            "ir.get",
            "ir.transact",
            "ir.lock",
            "ir.unlock",
            "dag.status",
            "dag.run",
            "gates.list",
            "gates.run",
            "plugins.list",
            "tools.list",
            "tools.call",
            "events.subscribe",
            "events.unsubscribe",
            "daemon.status",
            "daemon.shutdown",
        }

    # -- ir ----------------------------------------------------------------

    async def _m_ir_get(self, params: Any) -> dict[str, Any]:
        rev, value = self.store.read(params.path)
        return {"rev": rev, "value": value}

    async def _m_ir_transact(self, params: Any) -> dict[str, Any]:
        from atomc_core_ir import ConflictError, LockedError, PatchError, RefIntegrityError
        from pydantic import ValidationError as PydValidationError

        try:
            result = await self.store.transact(
                params.path, params.base_rev, params.ops, holder=params.holder
            )
        except ConflictError as exc:
            raise errors.RevisionConflictError(
                exc.current_rev, exc.expected_rev or params.base_rev
            ) from exc
        except LockedError as exc:
            raise errors.LockConflictError(
                exc.holder,
                exc.expires_at if isinstance(exc.expires_at, str) else str(exc.expires_at),
            ) from exc
        except PydValidationError as exc:
            raise errors.ValidationFailedError(validation_errors(exc)) from exc
        except RefIntegrityError as exc:
            raise errors.DanglingReferenceError(str(exc)) from exc
        except PatchError:
            raise
        self.events.publish(
            "ir.changed",
            {
                "rev": result.new_rev,
                "changed_paths": result.changed_paths,
                **({"holder": params.holder} if params.holder else {}),
            },
        )
        return {"new_rev": result.new_rev, "changed_paths": result.changed_paths}

    async def _m_ir_lock(self, params: Any) -> dict[str, Any]:
        from atomc_core_ir import LockedError

        try:
            expires_at = await self.store.lock(
                params.node, params.holder, params.ttl_s, reason=params.reason
            )
        except LockedError as exc:
            raise errors.LockConflictError(
                exc.holder,
                exc.expires_at if isinstance(exc.expires_at, str) else str(exc.expires_at),
            ) from exc
        return {"expires_at": expires_at}

    async def _m_ir_unlock(self, params: Any) -> dict[str, Any]:
        from atomc_core_ir import LockedError

        try:
            released = await self.store.unlock(params.node, params.holder)
        except LockedError as exc:
            raise errors.LockConflictError(
                exc.holder,
                exc.expires_at if isinstance(exc.expires_at, str) else str(exc.expires_at),
            ) from exc
        return {"released": released}

    # -- events ------------------------------------------------------------

    async def _m_events_subscribe(self, params: Any) -> dict[str, Any]:
        sub = self.events.subscribe(params.topics)
        if self.subscription_sink is not None:
            self.subscription_sink(sub)
        return {"subscription": sub.id}

    async def _m_events_unsubscribe(self, params: Any) -> dict[str, Any]:
        released = self.events.unsubscribe(params.subscription)
        if released and self.unsubscription_sink is not None:
            self.unsubscription_sink(params.subscription)
        return {"unsubscribed": released}

    # -- daemon ------------------------------------------------------------

    async def _m_daemon_status(self, params: Any) -> dict[str, Any]:
        state = self.runtime_state.read()
        age = self.runtime_state.age_ms()
        return {
            "pid": state.pid if state else None,
            "host": self.config.host,
            "port": self.config.port,
            "version": self.version,
            "project_root": str(self.config.project_root),
            "uptime_ms": age if age is not None else 0,
        }

    async def _m_daemon_shutdown(self, params: Any) -> dict[str, Any]:
        if self.on_shutdown is not None:
            outcome = self.on_shutdown()
            if inspect.isawaitable(outcome):
                await outcome
        return {"shutting_down": True}

    # -- plugins / dag / gates (populated by later modules) -----------------

    async def _m_plugins_list(self, params: Any) -> Any:
        if self.plugins is not None:
            return self.plugins.status_list()
        return []

    async def _m_dag_status(self, params: Any) -> Any:
        if self.dag is not None:
            return self.dag.status()
        return {"nodes": []}

    async def _m_dag_run(self, params: Any) -> Any:
        if self.dag is None:
            raise MethodNotFoundError("dag.run")
        run_id = await self.dag.run(targets=params.targets, force=params.force)
        return {"run_id": run_id}

    async def _m_gates_list(self, params: Any) -> Any:
        if self.gates is not None:
            return self.gates.list_results(ids=params.ids)
        return []

    async def _m_gates_run(self, params: Any) -> Any:
        if self.gates is None:
            raise MethodNotFoundError("gates.run")
        return await self.gates.run(ids=params.ids)

    async def _m_tools_list(self, params: Any) -> Any:
        if self.plugins is not None:
            return self.plugins.tools_list(agent=params.agent)
        return []

    async def _m_tools_call(self, params: Any) -> Any:
        if self.plugins is None:
            raise MethodNotFoundError("tools.call")
        return await self.plugins.call_tool(
            params.plugin, params.tool, params.args, holder=params.holder
        )


__all__ = [
    "JSONRPC_VERSION",
    "Dispatcher",
    "ParseOutcome",
    "RequestEnvelope",
    "dump",
    "error_response",
    "notification",
    "parse_message",
    "parse_params",
    "result_response",
    "validation_errors",
]
