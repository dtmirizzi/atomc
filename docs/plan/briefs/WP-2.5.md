# WP-2.5 `daemon-client-ts` — typed WebSocket RPC client

Read `_common.md`, PLAN §§2, 4, 5, 9 and `docs/architecture/contracts/rpc.md`, `ir-schema.md`, `plugin-manifest.md` fully. Contracts are frozen. WP-2.3 daemon and WP-2.1 SDK are implementing the server/manifest in separate paths. Build against the frozen protocol and mock server; coordinate integration only through handoff/API notes.

## Owned paths
- `packages/daemon-client/ts/**`
- `packages/daemon-client/README.md`

Do not edit daemon, plugin SDK, root workspace/lock, contracts or CI. List root lockfile needs in handoff.

## Deliverables
1. Package `@atomc/daemon-client`, ESM + DTS, catalog `ws`, `@types/ws`, `zod`, `vitest`, `typescript`, `tsup`; runtime dependency on `@atomc/core-ir: workspace:*`.
2. `DaemonClient.connect({url?, token?, timeoutMs?})`, `request<T>(method, params)`, typed method wrappers matching rpc.md, id correlation, concurrent in-flight requests, JSON-RPC server errors with typed classes (`RpcError`, `ConflictError`, `LockedError`, `ValidationError`, `PluginError`), malformed response handling, socket close/failure rejection, explicit `close()`.
3. Event `subscribe(topics, listener)` / unsubscribe support. Listener errors must not break the socket loop. Test event routing and subscription notifications.
4. `toRelativePatch(path, ops)` helper: normalize a base JSON Pointer and safely strip it from absolute pointers emitted by core-ir `patch(base)`; reject ops outside base; keep already-relative RFC 6902 ops valid. Unit tests with escaped `~0/~1`, root path, array paths, mismatch. Use the RPC contract's relative ops semantics.
5. `ensureDaemon(projectRoot, options?)`: read `~/.atomc/daemon.json`, validate pid/host/port/token and `/health`; reject stale pid file; when absent, spawn `uv run --project <repo> atomcd serve --project ...` with detached/logged child as appropriate; wait with bounded timeout and exponential backoff; never automatically retry mutating RPC requests. Use argv, avoid shell interpolation; never print bearer token. Provide injectable spawn/filesystem/clock for tests.
6. Tests with a deterministic mock JSON-RPC WS server (ephemeral loopback): request response IDs/out-of-order responses, RPC errors, notifications/events, timeout/close, patch path conversion, ensureDaemon lifecycle via mocked child and temp pidfile; no real daemon required.
7. `README.md`: usage, security/token behavior, daemon bootstrap, retry guarantees.

## Definition of done
`pnpm install --frozen-lockfile`, `pnpm --filter @atomc/daemon-client build test typecheck lint`, package coverage ≥85%, and `pnpm exec biome check packages/daemon-client/ts`. Handoff in `docs/plan/handoffs/WP-2.5.md`, commit and push `wp/2.5-daemon-client-ts`. Report root lockfile delta if any.
