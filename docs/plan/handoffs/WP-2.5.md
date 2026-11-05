# WP-2.5 `daemon-client-ts` — handoff

Branch: `wp/2.5-daemon-client-ts` · Status: **done, green** · Depends on: frozen
`docs/architecture/contracts/rpc.md` v0.1.0, `ir-schema.md`, `@atomc/core-ir` (types only).

## What was built

A new pnpm workspace package **`@atomc/daemon-client`** at `packages/daemon-client/ts`
(ESM + CJS + `.d.ts` via tsup) implementing the frozen RPC contract client surface.

- **`src/client.ts` — `DaemonClient`**
  - `DaemonClient.connect({url?, token?, timeoutMs?, onError?, WebSocketImpl?})`; default
    `ws://127.0.0.1:7437/rpc`, bearer token in the WS upgrade `Authorization` header.
  - `request<T>(method, params?)` with numeric id correlation and concurrent in-flight
    requests; responses are matched by id, unknown/duplicate ids ignored.
  - Typed wrappers matching `rpc.md`: `getIR`, `transact`, `lock`, `unlock`, `dagStatus`,
    `runDAG`, `listGates`, `runGates`, `listPlugins`, `listTools`, `callTool`,
    `daemonStatus`, `shutdown`.
  - `subscribe(topics, listener) → Subscription` (`events.subscribe`) with
    `unsubscribe()` (`events.unsubscribe`); wildcard `"*"` and empty-topic = all.
    Listener exceptions are caught and routed to `onError`, never breaking the socket loop.
  - `close()`; socket close/termination rejects all in-flight requests with
    `ConnectionClosedError`; `TimeoutError` per request and for connect; malformed
    JSON/envelope frames are reported via `onError` and never crash the loop.
- **`src/errors.ts` — typed error hierarchy**: `RpcError` (`code`, `data`) plus
  `ConflictError` (`-32010`), `LockedError` (`-32011`), `ValidationError` (`-32012`),
  `RefIntegrityError` (`-32013`), `PluginError` (`-32020`), `DagRunError` (`-32030`), and
  transport errors `ConnectionError`, `ConnectionClosedError`, `TimeoutError`,
  `MalformedResponseError`, `DaemonStartError`.
- **`src/patch.ts` — `toRelativePatch(base, ops)`**: normalizes the base pointer, strips it
  from absolute pointers emitted by core-ir `patch(base)` (boundary-aware, `~0`/`~1` safe),
  converts `move`/`copy` `from`, preserves already-relative ops, maps a pointer equal to the
  base to `""`, and throws `PatchPathError` for pointers targeting a different top-level IR
  node. Root base (`""`/`"/"`) is identity.
- **`src/ensure-daemon.ts` — `ensureDaemon(projectRoot, options?)`**: reads
  `~/.atomc/daemon.json` (mode 0600) and validates pid/host/port/token shape; reuses a live,
  healthy daemon (`GET /health`); deletes stale/unparseable/dead-pid files; otherwise spawns
  `uv run [--project <repo>] atomcd serve --project <projectRoot>` detached with argv (no
  shell), logging to `~/.atomc/daemon.log`; polls pid + health with bounded exponential
  backoff until `timeoutMs`, then kills the child and throws `DaemonStartError`. Spawn
  failures surface as `DaemonStartError` (no uncaught child `error` events). Process, fs,
  clock, health, and connect are injectable via `options.deps`. Never logs the bearer token
  and never retries mutating requests.
- **`src/types.ts`** — wire types for all RPC params/results, `GateResult` (gate-result.md),
  `PluginStatus`/`ToolInfo`, artifacts, and typed event payloads.
- **`README.md`** — usage, typed methods, errors, patch conversion, security/token behavior,
  explicit no-retry/no-reconnect guarantees, and daemon bootstrap.

## Tests (54 Vitest tests, 6 files)

- `test/client.test.ts` — request/response, out-of-order concurrent correlation, all typed
  error codes, malformed frames (array envelope, bad version, bad id, event without topic,
  empty response), unknown-id ignore, timeout, terminate/close rejection, auth token, wrong
  token, connect-refused and connect-timeout, and param shapes for every typed wrapper.
- `test/events.test.ts` — subscribe/route, wildcard, listener throw isolation, unsubscribe.
- `test/errors.test.ts` — every error constructor/parse path and `mapRpcError` mapping.
- `test/patch.test.ts` — prefix stripping, escaped `~0`/`~1`, root base, already-relative,
  base-equal, trailing slash, sibling/top-level rejection, invalid base/path, prefix-token.
- `test/ensure-daemon.test.ts` — reuse, stale dead pid, absent/corrupt pid file, health
  failure, backoff, timeout+kill, empty project root, no token in logs, `--project` omission.
- `test/ensure-daemon-defaults.test.ts` — real fs/pid/health/fetch/WS connect and real
  process spawn/timeout through the default dependency layer.
- `test/helpers/mock-server.ts` — deterministic ephemeral-loopback JSON-RPC WS server
  (scripted handler, `NO_RESPONSE`, `rpcError`, notifications, raw frames, terminate).

Coverage (v8): **92.77% stmts / 89.2% branches / 91.02% funcs / 95.55% lines** (threshold 85%).

## How to verify (exact commands, from repo root)

```bash
# Root lockfile must first gain the packages/daemon-client/ts importer (see below), then:
pnpm install --frozen-lockfile
pnpm --filter @atomc/daemon-client build
pnpm --filter @atomc/daemon-client test
pnpm --filter @atomc/daemon-client test:coverage
pnpm --filter @atomc/daemon-client typecheck
pnpm --filter @atomc/daemon-client lint
pnpm exec biome check packages/daemon-client/ts
```

All green locally on macOS arm64, Node 25, pnpm 10.30.3. Note: run the coverage command
last, or delete `packages/daemon-client/ts/coverage/` before the explicit biome check (the
generated coverage summary is a gitignored artifact that biome would otherwise format).

## Design decisions

- **Structural wire types, types-only core-ir dependency.** The brief mandates a runtime
  dependency on `@atomc/core-ir`; the client only needs its `JsonPatchOp` type, so all
  imports from it are `import type` (erased at runtime) while the package still declares
  `"@atomc/core-ir": "workspace:*"`.
- **One response per id, numeric ids.** The client issues monotonically increasing numeric
  ids and only matches numeric ids, per `rpc.md` ("server echoes `id` exactly").
- **No automatic reconnection/retry.** `rpc.md`/PLAN permit bounded retries only for safe
  reads; because a dropped socket can follow an applied mutation, the client exposes none by
  default and documents re-read-then-retry. This is an explicit decision, not an omission.
- **Inject-everything `ensureDaemon`.** `EnsureDaemonDeps` covers fs, spawn, pid liveness,
  health, connect, sleep, clock, and home dir, so pid/stale/spawn/backoff paths are tested
  without a real daemon. Two tests additionally exercise the real default layer.
- **Spawn error handling.** `SpawnedDaemon.error` is set from the child `error` event so
  `ensureDaemon` fails fast with `DaemonStartError` instead of emitting an uncaught
  exception, and never withholds a useful message.
- **`WebSocketImpl` injection** keeps the client testable without a daemon and allowed
  deterministic connect-timeout coverage.

## Deviations from contract

None. The client matches `rpc.md` method names/params/results, error codes, the `event`
notification shape, and the relative-ops semantics of `ir.transact`. `toRelativePatch`
resolves the WP-1.3 open issue by converting core-ir absolute pointers to RPC-relative ops
and rejecting out-of-base pointers before the request is sent.

## Open issues

- **Root lockfile importer required** (see below): cannot commit `pnpm-lock.yaml` per the
  manager's instruction.
- `@atomc/core-ir` must be built (`pnpm --filter @atomc/core-ir build`) before this
  package's `typecheck`/`build` resolve its `dist/index.d.ts` in a clean checkout; turbo's
  `build` graph handles this once the importer exists. Tests use type-only imports.
- WP-2.3 daemon implementation was not available in this worktree; the client was built and
  tested against the frozen contract and the mock server. WP-2.6 should exercise it against
  the real daemon.
- `errors.ts` `Retryable`/safe-read retry hooks were intentionally left out; if a later WP
  wants safe-read retries it should add them on top of `request` with an explicit method
  allow-list (mutations must never be retried).

## Root changes needed

- **`pnpm-lock.yaml`** — add exactly one importer for `packages/daemon-client/ts`:
  - dependencies: `@atomc/core-ir` → `link:../../packages/core-ir/ts`; `ws` → catalog `8.22.1`
  - devDependencies: `@types/node` catalog `25.9.9`; `@types/ws` catalog; `@vitest/coverage-v8`
    catalog; `tsup` catalog (`9.0.0(postcss@8.5.32)(tsx@4.23.15)(typescript@5.9.3)(yaml@2.9.1)`);
    `typescript` `^5.9.0` → `5.9.3` (same escape-hatch pin as `packages/core-ir/ts` for tsup
    DTS); `vitest` catalog. No new package resolutions, no catalog changes. This is the only
    root file change requested.
