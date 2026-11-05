# @atomc/daemon-client

Typed JSON-RPC 2.0 client for the atomc daemon (`atomcd`) over WebSocket, plus a
daemon bootstrap helper. Implements the frozen contract in
[`docs/architecture/contracts/rpc.md`](../../../docs/architecture/contracts/rpc.md).

## Install

```bash
pnpm add @atomc/daemon-client
```

ESM and CJS builds ship with `.d.ts` types. Runtime dependencies: `ws` and
`@atomc/core-ir` (for the JSON Patch op types).

## Usage

```ts
import { DaemonClient, toRelativePatch } from "@atomc/daemon-client";
// `patch(base)` comes from @atomc/core-ir and emits absolute pointers:
import { patch } from "@atomc/core-ir";

const client = await DaemonClient.connect({
  url: "ws://127.0.0.1:7437/rpc",
  token: process.env.ATOMCD_TOKEN,
});

// Typed method wrappers matching rpc.md.
const { rev, value } = await client.getIR("/electrical");

// core-ir patch(base) emits absolute pointers; the RPC wants them relative to path.
const ops = toRelativePatch("/electrical", patch("/electrical").add("/assertions/-", a).build());
const { new_rev } = await client.transact({ path: "/electrical", base_rev: rev, ops });

// Events (best-effort, ordered per connection; no durable replay).
const sub = await client.subscribe(["ir.changed", "gate.result"], (event) => {
  console.log(event.topic, event.data);
});
await sub.unsubscribe();

await client.close();
```

### Typed methods

`getIR`, `transact`, `lock`, `unlock`, `dagStatus`, `runDAG`, `listGates`,
`runGates`, `listPlugins`, `listTools`, `callTool`, `daemonStatus`, `shutdown`.
Anything else can go through `request<T>(method, params)`.

### Errors

Server errors map to typed classes: `ConflictError` (`-32010`), `LockedError`
(`-32011`), `ValidationError` (`-32012`), `RefIntegrityError` (`-32013`),
`PluginError` (`-32020`), `DagRunError` (`-32030`), and generic `RpcError`.
Transport failures use `ConnectionError`, `ConnectionClosedError`,
`TimeoutError`, and `MalformedResponseError`. All extend `DaemonClientError`.

### Patch path conversion

`toRelativePatch(base, ops)` strips the transaction base from absolute pointers
emitted by `@atomc/core-ir`'s `patch(base)`, leaves already-relative pointers
alone, and rejects pointers that target a different top-level IR node with
`PatchPathError`.

```ts
toRelativePatch("/electrical", [
  { op: "replace", path: "/electrical/assertions/0/status", value: "fail" },
]);
// => [{ op: "replace", path: "/assertions/0/status", value: "fail" }]
```

## Security and tokens

- The daemon writes `~/.atomc/daemon.json` with mode `0600`, containing a random
  bearer token (≥32 bytes). Pass it to `connect({ token })`.
- The token is sent only in the WebSocket upgrade `Authorization: Bearer …`
  header and is never logged by this client.
- Never print or commit `daemon.json`.

## Retries and reconnection

This client performs **no automatic reconnection and no automatic request
retries**. A timeout or socket close can happen after the daemon applied a
mutation, so retrying blindly risks double-applying a patch. Callers must re-read
(`ir.get`, `dag.status`, `gates.list`) and only then decide whether to retry;
`close()` rejects every in-flight request with `ConnectionClosedError`.

## Daemon bootstrap

```ts
import { ensureDaemon } from "@atomc/daemon-client";

const { info, started, client } = await ensureDaemon(process.cwd());
```

`ensureDaemon(projectRoot, options?)`:

1. Reads `~/.atomc/daemon.json` (mode `0600`) and validates the pid, host, port,
   and token shape.
2. Checks the pid is alive and that `GET http://host:port/health` returns
   `{ok: true}`. A live, healthy daemon is reused (`started: false`).
3. Deletes a stale/incomplete pid file (dead pid or failing health).
4. Spawns `uv run [--project <repo>] atomcd serve --project <projectRoot>` as a
   detached child using argv (no shell interpolation), logging to
   `~/.atomc/daemon.log`. Pass `uvProject` or set `ATOMC_REPO` for the repo.
5. Polls the pid file and health endpoint with bounded exponential backoff until
   `timeoutMs` (default 30 s), then kills the child and throws
   `DaemonStartError`.

The bearer token is read from the pid file and passed to
`DaemonClient.connect`; it is never written to the log sink. `ensureDaemon` never
retries mutating RPC requests. Process, filesystem, clock, health, and connect
behavior are injectable via `options.deps` for tests.

## License

Apache-2.0
