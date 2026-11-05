"""``atomcd`` Typer CLI: ``serve``, ``status``, ``stop`` and ``doctor``."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import time
from pathlib import Path
from typing import Annotated, Any, NoReturn

import httpx
import typer
import uvicorn

from . import VERSION
from .app import Services, create_app
from .config import DEFAULT_HOST, DEFAULT_PORT, DEFAULT_STATE_DIR, DaemonConfig
from .dag import CycleError, DagScheduler
from .events import EventBus
from .gates import GateRunner
from .ir_store import IRStore
from .logging import configure_logging, get_logger
from .plugins.discovery import build_registry
from .runtime import RuntimeState, load_state_file, pid_alive

app = typer.Typer(
    name="atomcd",
    help="atomc daemon: IR store, DAG scheduler, gate runner and JSON-RPC host.",
    no_args_is_help=True,
    add_completion=False,
)

StateDirOption = Annotated[
    Path,
    typer.Option("--state-dir", help="Directory holding daemon.json", envvar="ATOMCD_STATE_DIR"),
]
ProjectOption = Annotated[Path, typer.Option("--project", "-p", help="Project root directory")]
JsonOption = Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON")]


def _emit(payload: dict[str, Any], as_json: bool, lines: list[str] | None = None) -> None:
    if as_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    elif lines:
        for line in lines:
            typer.echo(line)
    else:
        for key, value in payload.items():
            typer.echo(f"{key}: {value}")


def _build_services(config: DaemonConfig) -> Services:
    runtime = RuntimeState(config.state_dir)
    runtime.clear_if_stale()
    store = IRStore(config.project_root)
    store.load()
    logger = get_logger("atomcd")
    events = EventBus()
    events.set_logger(logger)
    registry = build_registry(config.project_root, store=store, events=events, logger=logger)
    gates = GateRunner(registry=registry, store=store, events=events, logger=logger)
    dag: DagScheduler | None
    try:
        dag = DagScheduler(
            registry=registry, store=store, events=events, gate_runner=gates, logger=logger
        )
    except CycleError as exc:
        logger.error("dag_cycle_detected", error=str(exc))
        dag = None
    return Services(
        config=config,
        store=store,
        runtime_state=runtime,
        events=events,
        version=VERSION,
        dag=dag,
        gates=gates,
        plugins=registry,
        logger=logger,
    )


@app.command()
def serve(
    project: ProjectOption = Path("."),
    host: Annotated[str, typer.Option(envvar="ATOMCD_HOST")] = DEFAULT_HOST,
    port: Annotated[int, typer.Option(envvar="ATOMCD_PORT")] = DEFAULT_PORT,
    state_dir: StateDirOption = DEFAULT_STATE_DIR,
    json_output: JsonOption = False,
) -> None:
    """Start the daemon in the foreground."""
    configure_logging()
    config = DaemonConfig(host=host, port=port, state_dir=state_dir).with_project(project)
    existing = RuntimeState(config.state_dir).read()
    if existing is not None and pid_alive(existing.pid) and existing.pid != os.getpid():
        _emit(
            {"ok": False, "error": "daemon already running", "pid": existing.pid},
            json_output,
        )
        raise typer.Exit(code=1)

    services = _build_services(config)
    app_ = create_app(services)
    services.runtime_state.write(
        pid=os.getpid(),
        host=config.host,
        port=config.port,
        token=config.effective_token,
        project_root=str(config.project_root),
        version=VERSION,
    )
    _emit(
        {
            "ok": True,
            "pid": os.getpid(),
            "host": config.host,
            "port": config.port,
            "project_root": str(config.project_root),
        },
        json_output,
        [
            f"atomcd {VERSION} listening on http://{config.host}:{config.port} "
            f"(project {config.project_root})"
        ],
    )

    async def _run() -> None:
        server = uvicorn.Server(
            uvicorn.Config(app_, host=config.host, port=config.port, log_level="info")
        )

        async def _watch_shutdown() -> None:
            await services.shutdown_event.wait()
            server.should_exit = True

        watcher = asyncio.create_task(_watch_shutdown())
        try:
            await server.serve()
        finally:
            watcher.cancel()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:  # pragma: no cover - interactive
        pass
    finally:
        services.runtime_state.clear()


@app.command()
def status(
    state_dir: StateDirOption = DEFAULT_STATE_DIR,
    json_output: JsonOption = False,
) -> None:
    """Report whether a daemon is running for this state directory."""
    runtime = RuntimeState(state_dir)
    state = runtime.read()
    payload: dict[str, Any] = {"running": False}
    if state is None:
        payload["error"] = "no daemon.json"
    else:
        payload.update(
            {
                "pid": state.pid,
                "pid_alive": pid_alive(state.pid),
                "host": state.host,
                "port": state.port,
                "project_root": state.project_root,
                "version": state.version,
                "started_at": state.started_at,
            }
        )
        try:
            response = httpx.get(f"http://{state.host}:{state.port}/health", timeout=2.0)
            payload["health"] = response.json()
            payload["running"] = bool(response.json().get("ok"))
        except httpx.HTTPError as exc:
            payload["health_error"] = str(exc)
    _emit(payload, json_output)


@app.command()
def stop(
    state_dir: StateDirOption = DEFAULT_STATE_DIR,
    json_output: JsonOption = False,
) -> None:
    """Stop a running daemon by pid."""
    runtime = RuntimeState(state_dir)
    state = runtime.read()
    if state is None:
        _emit({"stopped": False, "reason": "no daemon.json"}, json_output)
        raise typer.Exit(code=1)
    if not pid_alive(state.pid):
        runtime.clear()
        _emit({"stopped": False, "reason": "stale pid removed"}, json_output)
        raise typer.Exit(code=1)
    try:
        os.kill(state.pid, signal.SIGTERM)
    except ProcessLookupError:  # pragma: no cover - race
        runtime.clear()
        _emit({"stopped": False, "reason": "process disappeared"}, json_output)
        return
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and pid_alive(state.pid):
        time.sleep(0.1)
    runtime.clear()
    _emit({"stopped": True, "pid": state.pid}, json_output)


@app.command()
def doctor(
    state_dir: StateDirOption = DEFAULT_STATE_DIR,
    json_output: JsonOption = False,
) -> None:
    """Check the daemon environment and Python kernel dependencies."""
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    import sys

    check("python", sys.version_info >= (3, 14), sys.version.split()[0])
    try:
        import atomc_core_ir

        check("core-ir import", True, getattr(atomc_core_ir, "__name__", "atomc_core_ir"))
    except ImportError as exc:  # pragma: no cover - defensive
        check("core-ir import", False, str(exc))
    for module in ("fastapi", "uvicorn", "networkx", "watchfiles", "structlog"):
        try:
            __import__(module)
            check(f"{module} import", True)
        except ImportError as exc:  # pragma: no cover - defensive
            check(f"{module} import", False, str(exc))
    state = RuntimeState(state_dir)
    check("state dir", state.state_dir.exists(), str(state.state_dir))
    payload = {"ok": all(c["ok"] for c in checks), "checks": checks}
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for item in checks:
            mark = "ok" if item["ok"] else "FAIL"
            typer.echo(f"[{mark}] {item['name']} {item['detail']}".rstrip())
        if not payload["ok"]:
            raise typer.Exit(code=1)


def main() -> NoReturn:
    """Console-script entry point."""
    app(prog_name="atomcd")
    raise SystemExit(0)


__all__ = ["app", "main"]


# ``load_state_file`` is exported for scripts/tests that inspect the pid file directly.
_ = load_state_file
