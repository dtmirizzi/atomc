# WP-2.6 `rpc-contract-tests` — real daemon/client contract suite

Read `_common.md`, PLAN §§2, 4, 6, 8, 9 and these contracts/handoffs fully:
`docs/architecture/contracts/rpc.md`, `ir-schema.md`, `plugin-manifest.md`, `gate-result.md`,
`docs/plan/handoffs/WP-2.3.md`, `WP-2.5.md`. Phase 2 integration PR #6 is merged to main. These
are **real daemon + real TypeScript client tests**, not another mock-server unit suite.

## Owned paths
- `tests/rpc/**`
- `docs/plan/handoffs/WP-2.6.md`

Do not modify daemon/client implementation, contracts, `pnpm-workspace.yaml`, `.github/**`, or root
lockfiles. If the new package needs workspace/CI/lock wiring (it will), report exact root changes in
handoff and ask the orchestrator for integration. You may add tests only under your ownership.

## Deliverables
1. Private pnpm package `@atomc/rpc-contract-tests` (`tests/rpc/package.json`) with Vitest, TypeScript,
   Node types, `@atomc/daemon-client: workspace:*`, and `ws` as needed. Scripts `contract`, `test`,
   `typecheck`, `lint`. Ask for (do not commit) root `pnpm-workspace.yaml` inclusion + lock importer.
2. Test harness in `tests/rpc/ts/fixtures/` and `harness.ts`:
   - create a fresh temp project directory and canonical minimal `system_ir.json` from core-ir fixture;
   - write a minimal Python fake plugin module and frozen-contract-valid `atomc-plugin.json` into the
     temp project. It registers one watch, one gate, one read tool and one mutating tool; the gate
     returns a deterministic PASS `GateResult`; the write tool mutates only its declared `/electrical`
     scope through host `ir_transact`;
   - choose a free localhost TCP port (port 0, discover actual port from daemon output/state);
   - spawn the actual daemon with `uv run --project <repo> atomcd serve --project <tmp-project>
     --port <free-port> --state-dir <tmp-state>` using argv, no shell. Wait for `/health` and
     `daemon.json`; read bearer token from the file (never print it). Use the actual
     `@atomc/daemon-client` against `ws://127.0.0.1:<port>/rpc`;
   - teardown in `finally`: call `daemon.shutdown` when possible, otherwise terminate child, wait,
     kill only if still alive, remove temp dirs. Capture bounded stdout/stderr and include them in
     failure messages with token redacted. Enforce startup/request/teardown timeouts.
3. Golden/contract tests, all using actual server + client:
   - HTTP `/health`, `/schema`; schema matches `@atomc/core-ir` generated version.
   - unauthenticated and bad bearer WebSocket requests fail policy close; valid bearer connects.
   - `ir.get` root and subtree: expected values/revisions; `ir.transact` valid patch increments
     document + owning-node revision, reports changed paths; stale base rev is `ConflictError`; bad
     patch yields `ValidationError`/`RefIntegrityError`, and data/revs stay unchanged; lock/unlock
     blocks another holder with `LockedError` and permits the holder.
   - `plugins.list`, `tools.list` allowlist filtering, declared read tool result, mutating tool scope
     write + revision update, attempts outside `produces` rejected.
   - `gates.run` and `gates.list` return/store a deterministic PASS `GateResult` at the contract IR
     path; a fake gate FAIL/advisory result does not crash the daemon.
   - `dag.status`, targeted `dag.run`, start/end events; subscribe/unsubscribe and `ir.changed`/gate
     event delivery. Use waits/polling with bounded timeouts, never timing sleeps alone.
   - `daemon.status`, `daemon.shutdown`, process exit and pid-file cleanup; stale pid-file behavior.
4. Determinism: no LLM, vendor services, Renode, CAD kernels or GUI. Temp fixtures, fake plugins,
   free local port, and fixed timestamps/data. Tests should be runnable on CI Ubuntu and macOS; skip
   only if the platform lacks a usable subprocess (document why).
5. README with exact commands and required environment (`uv`, Python 3.14, pnpm); handoff includes
   `pnpm-workspace.yaml` glob, `package.json`/Turbo/CI tasks if needed, and exact importer requirements.

## Definition of done
After orchestrator wires the workspace and lock importer:

```bash
pnpm install --frozen-lockfile
pnpm --filter @atomc/rpc-contract-tests contract
pnpm --filter @atomc/rpc-contract-tests typecheck
pnpm --filter @atomc/rpc-contract-tests lint
pnpm exec turbo run contract
```

All green locally and on CI (Linux + macOS where applicable). Every spawned process/temp directory is
cleaned even on assertion failure. Handoff at `docs/plan/handoffs/WP-2.6.md`; conventional commits and
push `wp/2.6-rpc-contract-tests`. Do not merge; orchestrator owns integration.
