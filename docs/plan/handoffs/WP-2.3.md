# WP-2.3 `daemon-core` — handoff

Branch `wp/2.3-daemon-core` · distribution `atomc-daemon` (`packages/daemon/python`) ·
module `src/atomcd`.

## What was built

All ten brief deliverables, plus the WP-2.4 kernel boundary:

1. **`atomc-daemon` distribution** (`packages/daemon/python`, hatchling, `src/atomcd`, `py.typed`).
   Deps: `atomc-core-ir`, FastAPI, uvicorn[standard], networkx, watchfiles, structlog, Typer,
   pydantic/settings, httpx. Console script `atomcd`.
2. **JSON-RPC 2.0 over WS** (`rpc.py`, `app.py`, `errors.py`): single-request semantics, batch
   rejected `-32600`, exact id echo, notifications get no reply, bearer auth before accept
   (missing/bad token closes `1008`), `GET /health`, `GET /schema`, `/openapi.json`, all frozen
   error codes (`-32010`…`-32013`, `-32020`, `-32030`, `-32603` opaque request id), token never
   logged.
3. **`IRStore`** (`ir_store.py`): load/create `system_ir.json`, in-memory validated `SystemIR`,
   canonical temp-file + fsync + atomic-replace writes, `read(path)` with node/document rev,
   `transact` via core-ir `apply_patch`, `lock`/`unlock`, and `map_upsert` for
   `/gates/results` + `/provenance/nodes`. All mutations serialised behind one `asyncio.Lock`;
   no write on conflict/validation/lock failure.
4. **Runtime files** (`runtime.py`): `~/.atomc/daemon.json` (mode `0600`, atomic), stale-pid
   cleanup on start and cleanup on shutdown, `pid`/host/port/token/project/start/version.
   `ATOMCD_HOST` / `ATOMCD_PORT` / `ATOMCD_STATE_DIR` / `ATOMCD_TOKEN` overrides.
5. **Plugin discovery** (`plugins/`): project `**/atomc-plugin.json` scan + `atomc.plugins`
   entry points; per-plugin fault isolation (bad manifest/handler only marks that plugin);
   global watch/gate/cli/ui id conflict detection; `plugins.list`.
6. **Reactive DAG** (`dag.py`): nodes = watches + gates; edges from `after` and
   `produces`↔`watches.ir` coverage; cycles rejected; incremental content-hash scheduling
   (IR subtree + file hashes + upstream outputs), topological order, per-node async locks,
   force/targeted runs, provenance writes, `dag.node.start/end` events, `ir.changed` hook,
   `watchfiles`-ready `notify_files_changed` with debounce.
7. **Gate runner** (`gates.py`): invokes declared handlers, normalises to frozen `GateResult`,
   stores at `/gates/results/<id-without-prefix>`, emits `gate.result`; advisory FAIL never
   blocks a DAG run; crashes become `ERROR` with sanitized evidence (stack stays in the log).
8. **Event bus** (`events.py`): topics, per-connection subscriptions, bounded queue (1024,
   drop-oldest + warning), best-effort/no durable replay, ordered per connection.
9. **`atomcd` CLI** (`cli.py`): `serve`, `status`, `stop`, `doctor`; `--project`, `--host`,
   `--port`, `--state-dir`, `--json`; `serve` handles SIGINT/SIGTERM via uvicorn and removes the
   pid file.
10. **Tests**: 130 daemon tests (HTTP, WS, golden JSON-RPC, store, plugins, DAG, gates, CLI,
    runtime, events, invoke, context, kernel protocol, logging) — **88 % line coverage**.
    Two SDK-only tests (valid manifest, invalid manifest rejected by the real SDK) use
    `pytest.importorskip("atomc_plugin_sdk")` so they run in the combined Phase-2 checkout and
    skip here. Fake plugin builders live in the importable
    `atomcd.testing` module (not `tests/fakes.py`), and every daemon test module is uniquely
    prefixed `test_daemon_*` so repo-root collection cannot hit pytest's duplicate-basename
    "import file mismatch" across packages; `uv run pytest packages/daemon/python/tests` from the
    repo root collects cleanly.

**Kernel boundary (WP-2.4):** `atomcd/kernel_protocol.py` defines `Kernel`, `KernelHealth`,
`KernelRegistry` and `KernelFactory` protocols only. No hardware engine is imported by the
daemon core; the file documents that OCP must run in a separate worker process and that kernels
are imported lazily by WP-2.4 under `atomcd/kernels/`.

## How to verify (exact commands)

```bash
uv sync --all-packages                       # after orchestrator regenerates uv.lock
uv run pytest packages/daemon/python/tests -q   # 130 passed, 2 skipped (real-SDK), from repo root
uv run pytest packages/daemon/python --cov=atomcd --cov-report=term-missing -q   # 88%
uv run ruff check packages/daemon/python
uv run ruff format --check packages/daemon/python
uv run mypy packages/daemon/python/src packages/daemon/python/tests packages/daemon/python/examples
uv run python -m compileall -q packages/daemon/python/src
pnpm exec turbo run contract                 # 30 cross-language tests, green
uv run python packages/daemon/python/examples/demo.py   # end-to-end transcript below
```

Repo-wide at handoff: `uv run pytest -q` → **186 passed, 2 skipped** (56 core-ir + 130 daemon),
identical under `--import-mode=importlib`; `uv run pytest packages/daemon/python/tests` from the
repo root → **130 passed, 2 skipped**;
`turbo run contract` → **30 passed**.

**Verified against the real SDK.** Installing `atomc-plugin-sdk` from `origin/wp/2.2-plugin-sdk-py`
with the shared schema from `origin/wp/2.1-plugin-sdk-ts` (via `ATOMC_PLUGIN_SCHEMA`, editable
`uv pip install`) and running the daemon suite yields **132 passed** — the SDK
`ManifestValidationError` path is translated and the two real-SDK regression tests execute.

## Demo transcript

`uv run python packages/daemon/python/examples/demo.py` (real `atomcd serve` subprocess on a
free port, fake plugin, token redacted):

```
# daemon.json: pid=5336 port=62541 token=<redacted>
# GET /health -> {"ir_rev": 0, "ok": true, "version": "0.0.1"}
# GET /schema -> title=SystemIR schema_version default=0.1.0
# ir.get / -> rev=0
# ir.transact /electrical -> new_rev=1 changed=['/electrical']
# stale ir.transact -> error -32010 {'current_rev': 1, 'expected_rev': 0}
# gates.run -> gate:demo.ok status=PASS
# dag.run -> run_id=run-2
# daemon.shutdown -> {'shutting_down': True}
# event <- gate.result {'status': 'PASS', 'summary': 'demo gate passed', 'id': 'gate:demo.ok', 'plugin': 'plugin:demo@0.1.0', 'severity': 'advisory', 'owner_agent': 'ee-agent', 'evaluated_at': '2026-11-05T00:51:58Z', 'ir_rev': 4, 'duration_ms': 0, 'evidence': [], 'suggestions': [], 'refs': []}
# event <- dag.node.end {'run_id': 'run-2', 'id': 'demo:refresh', 'ok': True, 'duration_ms': 0}
# pid file removed after shutdown: True
```

Note the `run_id` is `run-2` because the preceding `ir.transact` on `/electrical` invalidated the
`demo:refresh` watch and scheduled `run-1` automatically — evidence the DAG is reactive.

## Design decisions

- **Manifest loader is dual-path.** `plugins/manifest.py` implements the v0.1 contract locally
  *and* prefers `atomc_plugin_sdk.validate_manifest` when importable, so the daemon is green
  before WP-2.2 lands and shares one source of truth once it does.
- **SDK results are coerced, not passed to `Manifest.model_validate`.**
  `atomc_plugin_sdk.validate_manifest` returns the SDK's own `PluginManifest` class (a
  *different* Pydantic model), and may raise its own exception type or return a result carrying
  `issues`/`errors`. The daemon tries several normalisations in order —
  `model_dump(mode="python")`, `model_dump(mode="python", exclude_none=True)`,
  `model_dump(mode="json", by_alias=True)`, then legacy `.dict()` — and validates the first
  mapping the local models accept. SDK exceptions and non-empty issue lists become the daemon's
  `ManifestError`. Feeding the foreign model straight into `Manifest.model_validate` was the
  13-test integration failure. Regression coverage: fake-SDK injection tests (coercion, SDK
  exception translation, SDK-issues translation) plus two `pytest.importorskip("atomc_plugin_sdk")`
  tests that run only in the combined checkout with the real SDK installed.
- **Handler calling convention is arity-adapted** (`plugins/invoke.py`): gates get `(ctx)`,
  tools get `(ctx, args)`, watch handlers get `(ctx)`; sync and async both supported. This keeps
  the daemon independent of the still-in-flight Python SDK signatures.
- **IR pointer coverage is bidirectional for change routing** (`changed` ancestor/descendant of a
  watch pointer both invalidate) but one-directional for `produces` edges.
- **`dag.run` is asynchronous**: it returns `run_id` immediately and reports progress via events,
  matching the contract ("completion/progress arrives as events").
- **Provenance/gate writes** use `IRStore.map_upsert`, which reads the node rev under the write
  lock so callers never race the document revision.
- **`DEFAULT_STATE_DIR` expanded to `Path.home()/".atomc"`** at import so `doctor` checks the
  real directory.

## Deviations from contract

None observed. RPC methods, error codes/data, event topics, manifest field rules and
`GateResult` shape follow `docs/architecture/contracts/{rpc,plugin-manifest,gate-result,ir-schema}.md`
as written.

## Open issues

- **Plugin SDK integration exercised via a fake `atomc_plugin_sdk`.** The real package is not on
  this branch; the adapter path is unit-tested by injecting a foreign Pydantic model through
  `sys.modules`. After WP-2.1/2.2 merge, add a conformance test that validates the shared JSON
  Schema and exercises the real SDK return type.
- **Handler signatures are not yet the SDK's canonical ones.** Once WP-2.2 publishes
  `PluginHost`/handler typing, align `plugins/invoke.py` (and remove the arity heuristic if the
  SDK fixes the signature).
- **File watching is wired but not exercised in CI** (`notify_files_changed` + debounce is
  unit-tested directly); a real `watchfiles.awatch` loop in `serve` is a small WP-2.4/2.6 item if
  required. `Tool.input_schema` validation is not enforced by the daemon (SDK conformance owns
  it).
- **TS-only plugins are reported as `loaded=False`** with a clear error; a TS bridge is out of
  scope for the Python daemon.

## Root changes needed (orchestrator-owned)

1. **Regenerate `uv.lock`.** `uv.lock` is modified in the worktree but intentionally **not
   committed**. The exact needed changes are the new workspace member:

   ```
   [manifest members] add "packages/daemon/python"
   name = "atomc-daemon"
   source = { editable = "packages/daemon/python" }
   ```

   plus its dependency edges/lock entries for `atomc-core-ir`, `fastapi`, `uvicorn[standard]`,
   `networkx`, `watchfiles`, `structlog`, `typer`, `pydantic`, `pydantic-settings`, `httpx`.
   Run `uv lock` after merging the Phase-2 Python packages.
2. **No `pyproject.toml` / CI / workspace-file edits were made.** CI already globs
   `packages/*/python`, so `packages/daemon/python` is picked up automatically once the lock is
   regenerated.
3. **Cross-package test rename (done at orchestrator request).** `packages/core-ir/python/tests/`
   `test_schema.py` was renamed to `test_core_ir_schema.py` (content unchanged) because it
   collided by basename with `packages/plugin-sdk/python/tests/test_schema.py` under repo-root
   pytest's default import mode. Alternative single-line fix if preferred: add
   `--import-mode=importlib` to the root `[tool.pytest.ini_options] addopts`. Daemon test modules
   are already uniquely named `test_daemon_*`. This is the only change outside
   `packages/daemon/**` on this branch.
4. **Cross-package dependency not yet declared:** the brief asked to add `atomc-plugin-sdk` as a
   workspace dependency, but that package does not exist on this branch. It is currently an
   optional import (guarded, `# type: ignore[import-not-found]`). After WP-2.2 merges, add
   `atomc-plugin-sdk` to `packages/daemon/python/pyproject.toml` dependencies and remove the
   local-manifest fallback reliance (keep it as a fallback).
