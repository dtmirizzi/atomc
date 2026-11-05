# @atomc/rpc-contract-tests

Real **daemon ⇄ TypeScript client** contract tests for the atomc JSON-RPC surface
(`docs/architecture/contracts/rpc.md`, v0.1.0). Unlike
`packages/daemon-client/ts/test`, these tests do not use a mock server: each Vitest
file spawns the actual `atomcd serve` process and drives it through the real
`@atomc/daemon-client`.

## What it checks

- **HTTP** — `/health` shape and `/schema` byte-for-byte equality with the committed
  `packages/core-ir/schema/system_ir.schema.json` (the schema `@atomc/core-ir` is
  generated from).
- **Auth** — missing and incorrect bearer tokens close the WebSocket with policy
  code `1008`; a valid token connects and serves requests.
- **IR** — `ir.get` root/subtree revisions, `ir.transact` valid patches, stale
  `base_rev` conflicts (`-32010`), Pydantic validation failures (`-32012`), dangling
  references (`-32013`), and rollback (data and revisions unchanged on failure).
- **Locks** — `ir.lock`/`ir.unlock`, cross-holder contention (`-32011`), same-holder
  mutation, and unlock-then-reuse.
- **Plugins/tools** — `plugins.list`, `tools.list` agent allow-list filtering, a read
  tool result, a mutating tool that writes only its declared `produces` scope, and
  rejection (`-32020`) of a write outside that scope.
- **Gates** — `gates.run`/`gates.list`, deterministic `PASS` `GateResult` persisted at
  `/gates/results/<id-without-prefix>`, and advisory `FAIL` isolation.
- **DAG/events** — `dag.status`, targeted `dag.run`, `dag.node.start`/`dag.node.end`,
  `gate.result` and `ir.changed` delivery, and `events.unsubscribe`.
- **Lifecycle** — `daemon.status`, `daemon.shutdown`, process exit, pid-file removal
  and stale pid-file cleanup on start.

Everything is deterministic: no LLM, vendor service, Renode, CAD kernel or GUI. Each
test gets a fresh temp project with a canonical minimal `system_ir.json` and a fake
Python plugin (one watch, two gates, one read tool, one mutating tool).

## Requirements

- `uv` with Python 3.14 (the harness runs `uv run --project <repo> --all-packages atomcd serve`)
- `pnpm` 10 and Node ≥22
- the workspace must include `tests/rpc` (see "Root changes needed" in the handoff)

## Commands (from the repository root)

```bash
pnpm install --frozen-lockfile
pnpm --filter @atomc/rpc-contract-tests contract   # runs vitest, builds client deps first
pnpm --filter @atomc/rpc-contract-tests test
pnpm --filter @atomc/rpc-contract-tests typecheck
pnpm --filter @atomc/rpc-contract-tests lint
pnpm exec turbo run contract
```

`contract` and `test` are the same Vitest run. Each file spawns one daemon; files run
sequentially (`fileParallelism: false`) so the shared `uv` environment and the
free-port probe are never raced. Startup allows up to 180 s for the first `uv` sync;
per-test and hook timeouts are 300 s.

The harness terminates the daemon and deletes every temp directory in `afterAll`,
even when an assertion throws. Captured daemon stdout/stderr is bounded and always
token-redacted.
