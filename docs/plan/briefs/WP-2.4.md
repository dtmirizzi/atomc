# WP-2.4 `daemon-kernels` — warm hardware-engine registry

Read `_common.md`, PLAN §§1–2/6/8, and `docs/plan/handoffs/WP-0.1.md` plus `docs/plan/ENVIRONMENT.md`. Read WP-2.3's handoff and kernel-registry protocol before starting. This WP is **queued** until WP-2.3 commits that protocol; do not invent an interface early. Do not import kernels eagerly in `atomcd`.

## Owned paths
- `packages/daemon/python/src/atomcd/kernels/**`
- `packages/daemon/python/tests/kernels/**`
- `packages/daemon/docs/kernels.md`

## Deliverables (after WP-2.3 kernel protocol lands)
1. Registry adapters matching daemon's agreed `KernelRegistry` protocol: `health(name)`, `get(name)`, `reload(name)`, async lifecycle/shutdown; lazily initialize on first request and serialize startup per kernel.
2. Built-in optional kernel definitions for atopile/faebryk, build123d/OCP, pyrenode3/Renode, and kiutils/KiCad PCB parsing. No import of these libs at daemon module import/start unless configured. Missing optional dependency yields capability status `unavailable` with a useful reason; daemon remains healthy.
3. Process isolation for OpenCASCADE/build123d because OCP is not thread-safe. Use a supervised worker process with request IDs, bounded IPC, timeout/terminate/restart, and serialized jobs. Never fork a running multithreaded server unsafely; use spawn.
4. Renode adapter uses `PYRENODE_PATH` per WP-0.1 env docs, does not mix legacy aliases. QMK/QMK CLI are external subprocess tools and should be represented as a tool adapter, not imported as Python kernels.
5. Health/version reporting (kernel name, availability, version, cold/warm, last error, restart count), explicit shutdown, bounded logs; never leak credentials.
6. Tests use fake importers/process workers, monkeypatch optional dependency imports, verify lazy load, concurrent single initialization, missing-kernel behavior, reload, worker crash recovery, timeout/kill, graceful daemon shutdown. Keep CI independent of installed CAD/Renode packages.
7. Docs describe optional engines, environment variables, process isolation, and how plugins request a kernel.

## Definition of done
`uv run pytest packages/daemon/python/tests/kernels -q`, package Ruff/mypy clean, daemon suite remains green, no hardware library is imported by `import atomcd`. Handoff `docs/plan/handoffs/WP-2.4.md`, conventional commits, push `wp/2.4-daemon-kernels`. No root edits; request any daemon protocol adjustment from orchestrator/WP-2.3.
