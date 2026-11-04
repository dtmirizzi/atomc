# RPC methods

`atomcd` speaks JSON-RPC 2.0 over a WebSocket and exposes two HTTP endpoints. This page summarises the
surface; the [RPC contract](/architecture/contracts/rpc) is normative.

- **WebSocket:** `ws://127.0.0.1:7437/rpc` (override with `ATOMCD_PORT`)
- **HTTP:** `GET /health` → `{ok, version, ir_rev}` · `GET /schema` → IR JSON Schema
- **Auth:** a random token in `~/.atomc/daemon.json` (`{pid, port, token, project_root}`), sent as
  `Authorization: Bearer` on the WS upgrade

## Methods

| Method | Params | Result |
| ------ | ------ | ------ |
| `ir.get` | `{path?}` | `{rev, value}` |
| `ir.transact` | `{path, base_rev, ops, holder?}` | `TxResult{new_rev, changed_paths}` |
| `ir.lock` | `{node, holder, ttl_s, reason?}` | `{expires_at}` |
| `ir.unlock` | `{node, holder}` | `{}` |
| `dag.status` | `{}` | `{nodes:[{id, plugin, state, last_run?}]}` |
| `dag.run` | `{targets?, force?}` | `{run_id}` (progress via events) |
| `gates.list` | `{}` | `[GateResult]` |
| `gates.run` | `{ids?}` | `[GateResult]` |
| `plugins.list` | `{}` | `[PluginManifest + {loaded, error?}]` |
| `tools.list` | `{agent?}` | `[{plugin, name, description, input_schema}]` |
| `tools.call` | `{plugin, tool, args, holder?}` | `{result, artifacts?}` |
| `events.subscribe` | `{topics}` | `{subscription}` |
| `daemon.shutdown` | `{}` | `{}` |

## Error codes

| Code | Error |
| ---- | ----- |
| `-32010` | `Conflict{current_rev}` |
| `-32011` | `Locked{holder, expires_at}` |
| `-32012` | `Invalid{errors}` |

## Events

Subscribers receive server-pushed `event` notifications with `{topic, data}`:

- `ir.changed {rev, changed_paths, holder}`
- `gate.result` — a `GateResult`
- `dag.node.start {id}`
- `dag.node.end {id, ok, duration_ms}`
- `log {level, msg, plugin?}`
