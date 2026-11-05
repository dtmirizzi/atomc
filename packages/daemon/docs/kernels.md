# Warm hardware kernels (WP-2.4)

`atomcd.kernels` implements the warm-kernel registry declared by
[`atomcd.kernel_protocol`](../python/src/atomcd/kernel_protocol.py) (WP-2.3). The daemon core owns
the *interface*; this package provides lazy, optional adapters for the heavy hardware engines:

| Kernel | Engine | Import name(s) | Isolation |
|---|---|---|---|
| `atopile` | atopile / faebryk | `atopile` | in-process (version/availability only) |
| `kiutils` | KiCad `.kicad_pcb` parsing | `kiutils` | in-process (pure Python) |
| `ocp` | build123d / OCP | `build123d`, `OCP` | **spawn-ed worker process** |
| `renode` | pyrenode3 / Renode | `pyrenode3` | in-process (pythonnet) |

All four are **optional**. A daemon environment with none of them installed still starts, imports
`atomcd.kernels`, and reports each kernel as `unavailable`.

## Import-safety contract

`import atomcd` and `import atomcd.kernels` must never:

* import `atopile`, `faebryk`, `OCP`, `build123d`, `pythonnet`, `pyrenode3` or `kiutils`;
* spawn a process;
* run a hardware engine or touch a device.

Every heavy import happens inside a kernel's `_start()`. The OCP engine is imported in a *child*
process, never in the daemon. `packages/daemon/python/tests/test_kernels/test_import_safety.py`
enforces this in a fresh subprocess (no heavy modules in `sys.modules`, no
`multiprocessing.active_children()`).

## Protocol

`DefaultKernelRegistry` implements
[`KernelRegistry`](../python/src/atomcd/kernel_protocol.py):

```python
registry.register("ocp", OcpKernel)         # lazily instantiated by name
registry.names()                             # ["atopile", "kiutils", "ocp", "renode"]
kernel = registry.get("ocp")                 # handle, not necessarily started
kernel = await registry.ensure("ocp")        # started; concurrent cold starts serialize
health = await registry.health("ocp")        # never forces a start
new = await registry.reload("ocp")           # stop old handle, return a fresh cold one
await registry.shutdown()                    # stop every started kernel
```

`BaseKernel` supplies the per-kernel lifecycle. `start()` is idempotent and guarded by an
`asyncio.Lock`, so `asyncio.gather(k.start(), k.start(), ...)` performs exactly one cold start and
concurrent `call()`s cannot race a reload. `call(op, **kwargs)` starts the kernel on demand and
then dispatches to the adapter's `_call`.

### Health

`await kernel.health()` (or `registry.health(name)`) returns a `KernelHealthSnapshot`, which
structurally satisfies `KernelHealth` (`name`, `status`, `detail`) and adds:

| Field | Meaning |
|---|---|
| `status` | `unknown` / `starting` / `ready` / `error` / `stopped` (the protocol literal) |
| `availability` | `available` (ready) / `unavailable` (cold or missing deps) / `error` |
| `warm` | the engine is up |
| `version` | probed distribution version, when known |
| `last_error` | most recent start/stop failure |
| `restart_count` | times the registry replaced the kernel or the worker respawned |
| `cold_starts` | successful cold starts |

Health probes are cheap (`importlib.util.find_spec` + `importlib.metadata`), so asking for health
never pays the import cost. **A missing optional package yields `unavailable`, not `error`, and
never crashes the daemon.**

## Optional dependencies and environment

The hardware engines are *not* Python dependencies of `atomc-daemon`. Install them in the daemon
environment (or a dedicated kernel venv) when you want the corresponding kernel warm — see
`docs/plan/ENVIRONMENT.md`:

* atopile 0.15.9 (`uv tool install atopile==0.15.9`);
* build123d 0.13 / cadquery-ocp 8.0.1 (cp314 arm64 wheels);
* pyrenode3 (`git antmicro/pyrenode3@main`) + .NET 8 runtime + Renode 1.17.0;
* kiutils 1.4.8.

Environment variables:

| Variable | Kernel | Rule |
|---|---|---|
| `PYRENODE_PATH` | `renode` | **Only** supported Renode path variable. Points at the `Renode` binary. |
| `PYRENODE_BIN`, `PYRENODE_PKG` | — | Deprecated aliases. **Never set them**, and never combine them with `PYRENODE_PATH`; pyrenode3 raises `ImportError: Multiple Renode paths are set`. The adapter reports a clear error instead. |

`RenodeKernel(path=...)` sets only `PYRENODE_PATH` when the variable is absent. Tokens and other
secrets are never logged; kernel log records carry names, versions, counts and error text only.

## Isolation rationale (OCP)

OCP holds global C++ state that is not thread-safe, and `fork()`-ing a multithreaded daemon is
undefined behaviour. `atomcd.kernels.process.WorkerProcess` therefore uses an explicit
`multiprocessing.get_context("spawn")` child:

* one job at a time, serialized by a `threading.Lock`;
* JSON-compatible request/response metadata; geometry crosses the boundary by **STEP artifact
  path**, never inline, so the pipe stays bounded;
* a request id per call and a per-job timeout;
* on timeout or crash the worker is terminated and respawned up to `max_restarts` (default 3),
  with `restart_count`/`last_error` surfaced in health;
* `close()` sends a graceful shutdown message, joins, then hard-terminates if needed — no orphans
  (asserted by tests).

The worker protocol is deliberately small:

```
child  → parent  {"event": "ready"} | {"event": "startup_error", "error": {...}}
parent → child   {"id": 1, "op": "export_step", "kwargs": {...}}
child  → parent  {"id": 1, "ok": true, "result": {...}} | {"id": 1, "ok": false, "error": {...}}
parent → child   None            # graceful shutdown
```

`atomcd.kernels.worker_runner` is the child entrypoint. `atomcd.kernels.ocp_engine` is the real
build123d engine; `atomcd.kernels.testing` provides deterministic fake engines so the supervisor's
crash/timeout/restart paths are tested without any hardware package.

## Start / reload / error behaviour

| Situation | Result |
|---|---|
| Dependency missing | `start()` raises `KernelUnavailableError`; health `unavailable`; daemon continues |
| Import/engine error during start | `status=error`, `last_error` set, original exception re-raised |
| OCP worker crash mid-call | worker terminated + respawned; `WorkerCrashedError`; `restart_count++` |
| OCP worker timeout | worker terminated; `WorkerTimeoutError`; `restart_count++` |
| Worker returns structured error | `WorkerCallError`; worker stays alive, `restart_count` unchanged |
| `restart_count > max_restarts` | `WorkerStartError` |
| `reload(name)` | stops the old handle, returns a fresh cold handle with `restart_count + 1` |
| `shutdown()` | best-effort stop of every instantiated kernel |

QMK is **not** a kernel: `qmk compile` is an external subprocess tool owned by the QMK/firmware
plugins, so it is not registered here.

## Supported operations

| Kernel | Ops |
|---|---|
| `ocp` | `ping`, `version`, `make_box`, `export_step` (child process) |
| `kiutils` | `version`, `load`, `summary` (in-process) |
| `renode` | `version`, `add_machine`, `load_repl`, `start`, `pause`, `reset`, `quit`, `execute` |
| `atopile` | `version`, `ping` — `build` raises `KernelUnsupportedOperationError` |

atopile 0.15 exposes no supported public *build* API, so the adapter refuses to call an
undocumented internal function; Phase 4's `plugin-atopile` owns compilation (and may shell out to
the `ato` CLI). Unsupported ops always raise an explicit error — never a fake PASS.

## Local commands

```bash
# unit tests (no hardware packages required)
uv run pytest packages/daemon/python/tests/test_kernels -q
uv run pytest packages/daemon/python/tests -q

# import-safety
uv run python -c "import atomcd, atomcd.kernels; print('ok')"

# opt-in smoke against installed kernels
. ~/.atomc/env.sh
ATOMC_KERNEL_SMOKE=1 uv run pytest packages/daemon/python/tests/test_kernels/test_smoke_optional.py -q

# OCP child-process smoke (requires build123d; run outside pytest)
uv run python - <<'PY'
import asyncio
from atomcd.kernels.ocp import OcpKernel
async def main():
    k = OcpKernel()
    await k.start()
    print(await k.call("make_box", length=10, width=5, height=1.6))
    print(await k.call("export_step", path="/tmp/atomc-box.step"))
    print((await k.health()).to_dict())
    await k.stop()
asyncio.run(main())
PY
```

## Emulator results vs HIL

Renode gives a **regression aid** for CPU/peripheral behaviour; it is not proof that end-user USB
HID works, and a `renode` kernel that starts is not a matrix-scan or USB-enumeration result. The
adapter reports capability honestly (`unavailable`, `SKIP`-style detail) rather than a false
`PASS`. `fw.qmk_compile` is a deterministic software gate; USB HID, all-key reporting and
bootloader recovery are **hardware-in-the-loop** checks on a real board with the pogo fixture
(see `tests/hil/`, Phase 4–6) and are never claimed from emulation.
