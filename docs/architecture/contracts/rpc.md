# Contract: `atomcd` RPC (v0.1.0)

**Status: FROZEN for Phase 2.** Daemon, SDK, and TypeScript client implementations must conform to
this contract. Changes require orchestrator approval and golden-contract-test updates.

## Transport and lifecycle

- JSON-RPC 2.0 over WebSocket at `ws://127.0.0.1:7437/rpc`; override with `ATOMCD_HOST` and
  `ATOMCD_PORT`. HTTP endpoints share the same host/port.
- `GET /health` (unauthenticated) → `{ "ok": true, "version": "0.0.1", "ir_rev": 0 }`.
- `GET /schema` (unauthenticated) → committed `system_ir.schema.json` JSON Schema.
- `GET /openapi.json` → FastAPI OpenAPI document (diagnostics only; WS methods remain JSON-RPC).
- Start creates `~/.atomc/daemon.json` atomically with mode `0600`:
  `{pid, host, port, token, project_root, started_at, version}`. `daemon.status` checks pid and
  health before returning a live daemon. Stale pid files are deleted on start.
- WebSocket upgrade requires `Authorization: Bearer <token>`; rejected/missing token closes with
  policy code 1008. Token is random (at least 32 bytes), generated on daemon start, never logged.
- One request has one JSON-RPC response. Notifications have no response. Malformed JSON / invalid
  JSON-RPC envelope returns `-32700` / `-32600` respectively. Server echoes `id` exactly.

## Request / response methods

All params and results are JSON objects/arrays as shown; paths are RFC 6901 JSON Pointers.

| Method | Params | Result |
|---|---|---|
| `ir.get` | `{path?: string}` (default `/`) | `{rev: number, value: JSON}`; rev is document `meta.rev` for `/` or the owning node `_meta.rev` for a node path |
| `ir.transact` | `{path: string, base_rev: number, ops: JsonPatchOp[], holder?: string}` | `{new_rev, changed_paths}`; ops are relative to `path`, same as `core-ir` |
| `ir.lock` | `{node: string, holder: string, ttl_s: number, reason?: string}` | `{expires_at: RFC3339}` |
| `ir.unlock` | `{node: string, holder: string}` | `{released: true}` |
| `dag.status` | `{}` | `{nodes: [{id, plugin, state, last_run?}]}` where state is `idle|queued|running|ok|failed|stale` |
| `dag.run` | `{targets?: string[], force?: boolean}` | `{run_id}`; completion/progress arrives as events |
| `gates.list` | `{ids?: string[]}` | `GateResult[]` |
| `gates.run` | `{ids?: string[]}` | `GateResult[]` |
| `plugins.list` | `{}` | `PluginStatus[]` (`PluginManifest` plus `loaded`, optional `error`) |
| `tools.list` | `{agent?: string}` | `[{plugin, name, description, input_schema, mutates}]` filtered by agent allow-list if supplied |
| `tools.call` | `{plugin: string, tool: string, args: JSON, holder?: string}` | `{result: JSON, artifacts?: Artifact[]}` |
| `events.subscribe` | `{topics: string[]}` | `{subscription: string}`; subsequent pushes use the `event` notification below |
| `events.unsubscribe` | `{subscription: string}` | `{unsubscribed: true}` |
| `daemon.status` | `{}` | `{pid, host, port, version, project_root, uptime_ms}` |
| `daemon.shutdown` | `{}` | `{shutting_down: true}`; connection closes after response |

## Error mapping

JSON-RPC error object is `{code: number, message: string, data?: JSON}`. Required codes:

| Code | Meaning | `data` |
|---|---|---|
| `-32700` | parse error | optional byte/decoder detail |
| `-32600` | invalid request envelope | validation detail |
| `-32601` | method not found | `{method}` |
| `-32602` | invalid params | `{errors: [{path, message}]}` |
| `-32010` | optimistic revision conflict | `{current_rev, expected_rev}` |
| `-32011` | subtree lock conflict | `{holder, expires_at}` |
| `-32012` | IR/Pydantic validation failure | `{errors: [{path, message, type}]}` |
| `-32013` | dangling/duplicate IR reference | `{message, location?}` |
| `-32020` | plugin/tool failure | `{plugin, tool?, retryable, detail}` |
| `-32030` | DAG run failure | `{run_id, node?, detail}` |
| `-32603` | unexpected internal failure | opaque `request_id` only (full stack in daemon log) |

Errors must not include bearer token contents or secrets. `ir.transact` errors leave IR and revisions
unchanged. JSON-RPC batch requests are not supported in v0.1; reject them with `-32600`.

## Event notifications

A subscribed event is a JSON-RPC 2.0 notification:

```json
{"jsonrpc":"2.0","method":"event","params":{"topic":"ir.changed","data":{...}}}
```

Topics/data:

- `ir.changed`: `{rev, changed_paths, holder?}`
- `gate.result`: full `GateResult`
- `dag.node.start`: `{run_id, id, plugin}`
- `dag.node.end`: `{run_id, id, ok, duration_ms, error?}`
- `log`: `{level: debug|info|warning|error, msg, plugin?}` (no secrets)

Events are best-effort and ordered per WebSocket connection; reconnecting clients re-fetch state via
`ir.get`, `dag.status`, and `gates.list` (no durable replay in v0.1).

## TypeScript client surface

`@atomc/daemon-client` exports `DaemonClient.connect({url?, token?, timeoutMs?})`, `request(method,
params)`, typed helpers (`getIR`, `transact`, `lock`, `unlock`, `runDAG`, `listGates`, `runGates`,
`listPlugins`, `listTools`, `callTool`), `subscribe(topics, listener)`, and `close()`. A separate
`ensureDaemon(projectRoot)` helper reads/writes the pid file and starts `atomcd` via `uv` if needed.
Reconnection is bounded exponential backoff; requests are never automatically retried if the server
may have applied a mutation (clients may retry only after checking current revision).
