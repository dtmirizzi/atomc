# Contract: atomcd RPC (v0.1) — FROZEN for Phase 2 (draft visible to Phase 1)

Transport: JSON-RPC 2.0 over WebSocket `ws://127.0.0.1:7437/rpc` (port override `ATOMCD_PORT`).
HTTP: `GET /health` → `{ok, version, ir_rev}`; `GET /schema` → IR JSON Schema.
Auth: random token in `~/.atomc/daemon.json` (`{pid, port, token, project_root}`), sent as
`Authorization: Bearer` on WS upgrade.

| Method | Params | Result |
|--------|--------|--------|
| `ir.get` | `{path?: JSONPointer}` | `{rev, value}` |
| `ir.transact` | `{path, base_rev, ops, holder?}` | `TxResult{new_rev, changed_paths}` or error `-32010 Conflict{current_rev}` / `-32011 Locked{holder, expires_at}` / `-32012 Invalid{errors}` |
| `ir.lock` | `{node, holder, ttl_s, reason?}` | `{expires_at}` |
| `ir.unlock` | `{node, holder}` | `{}` |
| `dag.status` | `{}` | `{nodes:[{id, plugin, state: idle|queued|running|ok|failed|stale, last_run?}]}` |
| `dag.run` | `{targets?: [node id], force?: bool}` | `{run_id}` (progress via events) |
| `gates.list` | `{}` | `[GateResult]` |
| `gates.run` | `{ids?: [gate id]}` | `[GateResult]` |
| `plugins.list` | `{}` | `[PluginManifest + {loaded, error?}]` |
| `tools.list` | `{agent?}` | `[{plugin, name, description, input_schema}]` |
| `tools.call` | `{plugin, tool, args, holder?}` | `{result, artifacts?: [Artifact]}` |
| `events.subscribe` | `{topics: [str]}` | `{subscription}`; server pushes notifications `event` with `{topic, data}` |
| `daemon.shutdown` | `{}` | `{}` |

Event topics: `ir.changed {rev, changed_paths, holder}`, `gate.result GateResult`,
`dag.node.start {id}`, `dag.node.end {id, ok, duration_ms}`, `log {level, msg, plugin?}`.
