# `atomc-daemon` (`atomcd`)

The atomc daemon owns one project's **system IR**, the reactive **DAG scheduler**, the **gate
runner**, plugin discovery and an authenticated **JSON-RPC 2.0** host. It is the single writer
for `system_ir.json`; clients (CLI, Studio, swarm harness) mutate the IR through transactions.

Hardware kernels (atopile, OCP/build123d, pyrenode3, kiutils) are **not** imported by the daemon
core. `atomcd.kernel_protocol` defines the registry boundary implemented by WP-2.4.

## Install / run

```bash
uv sync --all-packages
uv run atomcd serve --project ./my-board        # foreground daemon
uv run atomcd status                            # is it running?
uv run atomcd stop
uv run atomcd doctor
```

Runtime state lives at `~/.atomc/daemon.json` (mode `0600`): pid, host, port, bearer token,
project root, start time and version. Override host/port with `ATOMCD_HOST` / `ATOMCD_PORT` and
the state directory with `ATOMCD_STATE_DIR`.

## HTTP

| Endpoint | Auth | Result |
|---|---|---|
| `GET /health` | none | `{ok, version, ir_rev}` |
| `GET /schema` | none | committed `system_ir.schema.json` |
| `GET /openapi.json` | none | FastAPI OpenAPI (diagnostics) |
| `WS /rpc` | `Authorization: Bearer <token>` | JSON-RPC 2.0 |

WebSocket upgrades without a valid bearer token are closed with policy code `1008`.

## JSON-RPC examples

```bash
# token from ~/.atomc/daemon.json
TOKEN=$(python -c 'import json;print(json.load(open("'"$HOME"'/.atomc/daemon.json"))["token"])')
```

Read the whole IR:

```json
{"jsonrpc":"2.0","id":1,"method":"ir.get","params":{"path":"/"}}
```

Apply a JSON Patch relative to `/electrical` (optimistic concurrency):

```json
{"jsonrpc":"2.0","id":2,"method":"ir.transact",
 "params":{"path":"/electrical","base_rev":0,
           "ops":[{"op":"add","path":"","value":{"_meta":{"rev":0,"lock":null},
                   "source":{"kind":"atopile","entry":"main.ato:App"}}}]}}
```

Errors use the frozen codes in `docs/architecture/contracts/rpc.md` (`-32010` revision conflict,
`-32011` lock conflict, `-32012` validation failure, `-32013` dangling reference, …). Batch
requests are rejected with `-32600`.

Subscribe to events (one response, then `event` notifications until unsubscribe):

```json
{"jsonrpc":"2.0","id":3,"method":"events.subscribe","params":{"topics":["ir.changed","gate.result"]}}
```

Events are best-effort, ordered per connection and **not replayed**: reconnect and re-fetch with
`ir.get` / `dag.status` / `gates.list`. Each connection has a bounded queue (1024); on overflow the
oldest event is dropped and a warning is logged.

## Layout

| Module | Responsibility |
|---|---|
| `config.py` | host/port/project/state + env overrides |
| `runtime.py` | `~/.atomc/daemon.json` lifecycle, stale-pid cleanup |
| `ir_store.py` | in-memory IR + atomic persistence + transactions |
| `events.py` | bounded event bus and subscriptions |
| `rpc.py` | envelope parsing, param models, method dispatch, error mapping |
| `app.py` | FastAPI app: `/health`, `/schema`, authenticated `/rpc` |
| `kernel_protocol.py` | `Kernel` / `KernelRegistry` interface for WP-2.4 |
| `cli.py` | `atomcd serve/status/stop/doctor` |

## Tests

```bash
uv run pytest packages/daemon/python -q
uv run ruff check packages/daemon/python
uv run mypy packages/daemon/python/src packages/daemon/python/tests
```
