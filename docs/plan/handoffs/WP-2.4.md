# WP-2.4 `daemon-kernels` — handoff

Branch `wp/2.4-daemon-kernels` · package `packages/daemon/python/src/atomcd/kernels/**` ·
docs `packages/daemon/docs/kernels.md`.

## What was built

The warm hardware-kernel layer behind the WP-2.3 boundary
(`atomcd/kernel_protocol.py`). All six brief deliverables:

1. **`DefaultKernelRegistry`** (`kernels/registry.py`) implements the merged `KernelRegistry`
   protocol: lazy instantiation by name, one serialized cold start per kernel (`ensure`), health
   that never forces a start, `reload` (stop old → fresh cold handle, `restart_count + 1`) and
   best-effort async `shutdown`. `health_all()` returns snapshots for every registered kernel.
2. **`BaseKernel`** (`kernels/base.py`) lifecycle: idempotent `start`/`stop` guarded by an
   `asyncio.Lock`, `call` auto-start, four extension hooks `_probe`/`_start`/`_stop`/`_call`.
   `KernelHealthSnapshot` (`kernels/health.py`) satisfies `KernelHealth` and adds
   `availability` (`available`/`unavailable`/`error`), `version`, `warm`, `last_error`,
   `restart_count`, `cold_starts`.
3. **Four optional adapters** (`kernels/builtin.py` registers them):
   * `atopile` — version/availability + `ping`; `build` raises
     `KernelUnsupportedOperationError` (no supported public atopile 0.15 build API; no internal
     function is called). Phase 4's `plugin-atopile` owns compilation.
   * `kiutils` — in-process pure-Python `.kicad_pcb` parsing (`version`, `load`, `summary`).
   * `ocp` — build123d/OCP **in a supervised `spawn` worker process** (`kernels/process.py` +
     `kernels/worker_runner.py` + `kernels/ocp_engine.py`): serialized jobs, request ids, bounded
     JSON IPC, geometry by STEP path, timeout/terminate/respawn, `max_restarts`, no-fork spawn.
   * `renode` — pyrenode3 using **only** `PYRENODE_PATH`; the deprecated `PYRENODE_BIN`/
     `PYRENODE_PKG` aliases are detected and rejected, never set or combined.
4. **Import safety** proven by a subprocess test: `import atomcd`, `import atomcd.kernels` and
   `import atomcd.kernels.builtin` pull in none of atopile/faebryk/OCP/build123d/pyrenode3/
   pythonnet/kiutils and spawn no process. Missing packages → `unavailable`, daemon keeps running.
5. **QMK is not a kernel.** `qmk compile` stays an external subprocess tool owned by the
   QMK/firmware plugins; nothing QMK-related is registered here.
6. **Docs** at `packages/daemon/docs/kernels.md`: protocol, isolation rationale, optional deps,
   env vars, start/reload/error table, local smoke commands, and an explicit emulator-vs-HIL
   boundary (USB HID / all-key / bootloader recovery are HIL, never claimed from Renode).

Tests use fake importers, fake `pyrenode3`/`kiutils`/`atopile` modules injected via `sys.modules`,
and a real spawned worker running `atomcd.kernels.testing:make_fake_engine` (crash/timeout/restart
paths). No hardware package is required in CI.

## How to verify (exact commands)

```bash
uv run pytest packages/daemon/python/tests/test_kernels -q     # 72 passed, 1 skipped (opt-in smoke)
uv run pytest packages/daemon/python/tests -q                  # 199 passed, 1 skipped
uv run ruff check packages/daemon/python
uv run ruff format --check packages/daemon/python
uv run mypy --strict packages/daemon/python/src/atomcd
uv run python -c "import atomcd, atomcd.kernels"

# coverage
uv run pytest packages/daemon/python/tests -q --cov=atomcd --cov-report=term   # atomcd 87%
uv run pytest packages/daemon/python/tests/test_kernels -q --cov=atomcd.kernels # kernels 87%

# opt-in, only on a host with the kernels installed:
. ~/.atomc/env.sh
ATOMC_KERNEL_SMOKE=1 uv run pytest packages/daemon/python/tests/test_kernels/test_smoke_optional.py -q
```

Observed at handoff: kernel tests **72 passed, 1 skipped**; full daemon suite **199 passed,
1 skipped**; `atomcd` coverage **87 %** (≥85 % floor), kernels package **87 %** (the OCP child and
worker loop are not traced in-process by design — they run under `spawn`).

## Design decisions

- **Health tri-state, not a new status literal.** The merged protocol's `KernelStatus` is
  fixed, so missing optional packages map to `status="stopped"` + `availability="unavailable"`;
  real start failures map to `status="error"` + `availability="error"`. No contract change needed.
- **Worker supervision is generic and testable.** `WorkerProcess` takes a dotted
  `module:factory` path and uses a real `spawn` context; tests point it at
  `atomcd.kernels.testing:make_fake_engine` so crash (op `crash` → `os._exit`), timeout (`sleep`),
  restart and no-orphan behavior are exercised with genuine processes and zero hardware.
- **`atomcd.kernels.testing`** (mirroring the existing `atomcd.testing`) is importable so a
  spawned child can resolve the fake factory by name; it also holds `CountingKernel` for the
  lifecycle tests.
- **OCP ops are intentionally minimal** (`ping`, `version`, `make_box`, `export_step`) and
  geometry is returned as a STEP path plus volume/bbox metadata — the shape of the later
  plugin-cad-jig integration, but not that plugin's scope.
- **atopile build is refused, not faked.** Reusing an undocumented internal function would be
  brittle; the adapter documents the CLI-subprocess path instead.

## Deviations from contract

None. RPC/manifest/IR/gate contracts are untouched. `atomcd/kernel_protocol.py` is used as-is
(read-only); no existing `atomcd` files outside `kernels/` were modified.

## Open issues

- **OCP/atopile/pyrenode3 engines are untested against the real packages in CI** (by design:
  CI installs none of them). The opt-in `test_smoke_optional.py` and the OCP snippet in
  `docs/kernels.md` are the local verification path. `ocp_engine.make_box`/`export_step` should be
  run once locally before `plugin-cad-jig` (Phase 4) relies on the op names.
- **Child-process coverage is 0 % in-process** for `worker_runner`/fake engines because coverage
  does not trace `spawn`ed children. If the daemon wants a numeric floor for child code, enable
  `COVERAGE_PROCESS_START` / `coverage.parallel = true` in a later CI WP; the behavior itself is
  covered by real-process tests.
- **Kernel registration is not yet wired into `atomcd serve`.** The daemon core (WP-2.3) does not
  call `create_default_registry()`; this WP delivers the registry per the brief's ownership rules.
  Wiring it into `Services`/`atomcd doctor` is a small follow-up for the daemon/app owner.
- **`renode` `_monitor.execute("quit")` on stop** is best-effort; pyrenode3's exact teardown
  semantics for a live emulation were not exercised (package absent in CI).

## Root changes needed (orchestrator-owned)

None. No new runtime dependencies, no `pyproject.toml`/lock/CI/workspace edits. `uv sync
--all-packages` and all DoD commands ran clean on the existing lockfile.
