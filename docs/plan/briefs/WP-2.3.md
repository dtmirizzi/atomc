# WP-2.3 `daemon-core` — atomcd storage, plugin host, DAG, gates, RPC

Read `_common.md`, `PLAN.md` §§1–6 and 9, `docs/architecture/contracts/ir-schema.md`, `plugin-manifest.md`, `rpc.md`, and `gate-result.md` completely. RPC and manifest v0.1 contracts are frozen. The TS/Python SDK and TS client agents are working in parallel in separate packages; depend only on their published interfaces and list any integration blockers in handoff. Do not implement CAD/firmware kernels in this WP: expose the kernel registry protocol for WP-2.4.

## Owned paths
- `packages/daemon/python/**`
- `packages/daemon/README.md`
- `packages/daemon/tests/**`

Do not edit root `pyproject.toml`, `uv.lock`, CI workflows, plugin SDK paths or contracts. List needed root changes in handoff.

## Deliverables
1. `atomc-daemon` Python distribution (`packages/daemon/python`, hatchling, `src/atomcd`). Deps: FastAPI, uvicorn, websockets/Starlette, pydantic (through core-ir), networkx, watchfiles, structlog, latest stable compatible versions per PLAN §2. Add `atomc-core-ir` and `atomc-plugin-sdk` as uv workspace dependencies; coordinate lockfile with orchestrator if needed.
2. Typed error/message layer implementing JSON-RPC 2.0, correlation ids, exact error codes/data in `rpc.md`, single-request WS semantics (reject batch), bearer token auth before accepting the WS, `GET /health`, `/schema`, `/openapi.json`, and daemon status/shutdown methods. Never log tokens; unexpected failures return opaque request id only and keep stack in logs.
3. `IRStore`: load/create `system_ir.json`, canonical writes via temp-file + fsync + atomic replace, in-memory validated `SystemIR`, read API, `apply_patch` wrapper using the core IR transaction functions, document/node rev reporting, no write on failed validation/conflict/lock. Serialize mutations behind a narrow async lock; test parallel conflicts.
4. Persistent runtime files under `~/.atomc/daemon.json` with restrictive mode (0600), pid/port/token/project root/start/version; stale pid detection, startup cleanup and shutdown cleanup. Bind localhost by default. Env overrides per RPC contract.
5. Plugin discovery: scan project and installed entry points `atomc.plugins` for `atomc-plugin.json`; consume SDK manifest loader and validate runtime entrypoints; expose `plugins.list`; isolate plugin load errors so one bad plugin does not prevent daemon health. Plugin context delegates IR transactions with declared produces scope enforcement.
6. Reactive DAG scheduler using networkx. Nodes = watch ids; derive edges from `watches.ir` to `produces` and explicit `after`; reject cycles. Run matching downstream nodes on `ir.changed`/file watcher events with debounce, topological ordering, per-node async lock, force/targeted run, content/input hash provenance. Provide deterministic fake plugins and fake executor; do not import hardware engines.
7. Gate runner: call declared plugin gate handlers, store `GateResult` in IR at `/gates/results/...`, emit gate event; ensure advisory FAIL does not turn a DAG run into blocking failure; crash becomes ERROR with sanitized evidence.
8. Event bus and WS subscriptions: topics, per-connection subscriptions, `ir.changed`, `gate.result`, `dag.node.start/end`, `log`; bounded queue/backpressure policy documented, no durable replay.
9. `atomcd` Typer CLI (or an entrypoint subcommand) `serve`, `status`, `stop`, `doctor`; CLI supports `--project`, `--host`, `--port`, JSON output. `serve` handles SIGINT/SIGTERM gracefully.
10. Tests: API health/schema/auth/errors; store roundtrip/atomic persistence/revision/rollback/locks; JSON-RPC golden requests; plugin discovery + scope enforcement; DAG edge/cycle/incremental behavior; gate result storage/events; subscribe/unsubscribe/shutdown; async concurrency. Use `httpx` TestClient/websockets ASGI test tools, no external ports except an opt-in smoke.

## Kernel boundary (for WP-2.4)
Add `KernelRegistry` Protocol/interface only: `health(name)`, `get(name)`, `reload(name)`, async context/worker contract. Initially register no real kernels; a fake kernel proves adapter life-cycle. Document that OCP uses a separate worker process and runtime kernel dependencies live in the bootstrap/daemon environment, not imported eagerly at daemon import.

## Definition of done
`uv sync --all-packages`, daemon pytest, Ruff, strict mypy; `pnpm exec turbo run contract` remains green. Add README with start/RPC examples and `docs/plan/handoffs/WP-2.3.md`. Commit/push branch `wp/2.3-daemon-core`. Before final handoff, provide a demo transcript: start temp project daemon, health/schema, `ir.get`, valid `ir.transact`, stale conflict, run fake DAG/gate, receive event, shutdown, pidfile removed.
