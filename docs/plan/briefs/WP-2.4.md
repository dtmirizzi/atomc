# WP-2.4 `daemon-kernels` — optional warm hardware-engine adapters

Read `_common.md`, PLAN §§1–2/6/8/9, `docs/plan/ENVIRONMENT.md`, `docs/plan/handoffs/WP-0.1.md`, and
`docs/plan/handoffs/WP-2.3.md` fully. WP-2.3 is merged; use the actual protocol in
`packages/daemon/python/src/atomcd/kernel_protocol.py` (do not invent another one). Daemon CI must
work without hardware engines installed.

## Owned paths
- `packages/daemon/python/src/atomcd/kernels/**`
- `packages/daemon/python/tests/test_kernels/**`
- `packages/daemon/docs/kernels.md`

No root lock/workspace edits, no edits to existing `atomcd` files outside the kernel package/tests,
and no edits to frozen contracts. Runtime dependency additions require orchestrator approval; kernels
must remain optional and lazy-load.

## Deliverables
1. Implement adapters matching the merged `Kernel`, `KernelHealth`, `KernelRegistry`, `KernelFactory`
   Protocols; inspect the current protocol before coding. The registry lazily instantiates by name,
   serializes concurrent cold starts per kernel, reports `available|unavailable|error`, version,
   cold/warm, last error and restart count, supports reload and async shutdown.
2. Optional definitions for:
   - atopile/faebryk (version/availability and a `run` adapter only if a supported public API is
     available; do not depend on an undocumented internal function without isolating it);
   - build123d/OCP **in a supervised spawn worker process**, because OCP is not thread-safe; bounded
     JSON/pickle IPC (prefer JSON for request/response metadata, STEP artifact path for geometry),
     request id, timeout, terminate/restart, serialized jobs. Never fork a multithreaded daemon.
   - pyrenode3/Renode using only `PYRENODE_PATH` from the environment guide; never combine the
     deprecated path aliases. Provide health/start/stop and an execution adapter if its public API
     supports it; otherwise report explicit capability-unavailable, not a fake PASS.
   - kiutils pure Python PCB parsing adapter (no KiCad GUI dependency).
3. Import-safety requirement: `import atomcd` and `import atomcd.kernels` must not import atopile,
   OCP/build123d, pythonnet/Renode, kiutils, or spawn processes. `KernelRegistry.health()` with a
   missing optional package returns `unavailable` and does not crash daemon startup.
4. QMK and `qmk compile` are external subprocess tools, not Python kernels. Do not add QMK to the
   registry unless an explicit tool-adapter API is agreed with the daemon/client owner.
5. Tests use fake importers/process workers and monkeypatches; cover lazy first load, concurrent
   single initialization, missing module, health/version, reload, worker timeout/crash/restart,
   shutdown, cleanup/no orphan, `PYRENODE_PATH` configuration and no-secret logs. Normal CI requires
   no hardware packages. Add a clearly marked opt-in smoke test guarded by an env variable only if
   installed local kernels provide a reliable public smoke surface.
6. Docs at `packages/daemon/docs/kernels.md`: protocol, isolation rationale, optional dependencies,
   env vars, start/reload/error behavior, local smoke commands, explicit distinction between
   emulator tests and HIL/USB proof.

## Definition of done
From root after the package is wired (no dependency additions expected):

```bash
uv run pytest packages/daemon/python/tests/test_kernels -q
uv run pytest packages/daemon/python/tests -q
uv run ruff check packages/daemon/python
uv run ruff format --check packages/daemon/python
uv run mypy --strict packages/daemon/python/src/atomcd
uv run python -c "import atomcd, atomcd.kernels"
```

All pass with zero optional kernel packages installed in CI. Handoff at `docs/plan/handoffs/WP-2.4.md`,
conventional commits, push `wp/2.4-daemon-kernels`. Do not merge.
