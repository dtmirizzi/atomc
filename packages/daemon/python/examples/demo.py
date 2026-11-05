"""End-to-end ``atomcd`` demo: real server, HTTP health/schema, WebSocket JSON-RPC.

Run from the repository root::

    uv run python packages/daemon/python/examples/demo.py

It creates a throwaway project with a fake plugin, starts ``python -m atomcd serve`` on a free
port, then exercises health, schema, ``ir.get``, a valid transaction, a stale-revision conflict,
``gates.run``, a DAG run with events, and ``daemon.shutdown`` — verifying the pid file is removed.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, cast

import httpx
from websockets.sync.client import connect

PLUGIN_MODULE = '''\
"""Fake plugin used by the demo (no hardware engines)."""


class DemoPlugin:
    def check_ok(self, ctx):
        return {"status": "PASS", "summary": "demo gate passed"}

    def refresh(self, ctx):
        return "refreshed"


plugin = DemoPlugin()
plugin.__atomc_node_handlers__ = {"demo:refresh": plugin.refresh}
'''

MANIFEST = {
    "manifest_version": "0.1.0",
    "name": "demo",
    "version": "0.1.0",
    "description": "demo plugin",
    "atomc": ">=0.0.1 <0.2.0",
    "runtime": {"python": "demo_plugin:plugin"},
    "watches": [{"id": "demo:refresh", "ir": ["/electrical"], "files": [], "debounce_ms": 0}],
    "produces": ["/sourcing"],
    "gates": [
        {
            "id": "gate:demo.ok",
            "severity": "advisory",
            "owner_agent": "ee-agent",
            "after": ["demo:refresh"],
            "handler": "check_ok",
        }
    ],
    "tools": [],
    "cli": [],
    "ui": [],
}

ELECTRICAL = {
    "_meta": {"rev": 0, "lock": None},
    "source": {"kind": "atopile", "entry": "main.ato:App"},
    "components": [],
    "nets": [],
    "assertions": [],
    "erc": [],
}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def rpc(
    ws: Any,
    method: str,
    params: dict[str, Any] | None,
    req_id: int,
    collected: list[dict[str, Any]],
) -> dict[str, Any]:
    ws.send(json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}))
    while True:
        message = json.loads(ws.recv())
        if message.get("method") == "event":
            collected.append(message)
            continue
        return cast("dict[str, Any]", message)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        project = root / "project"
        (project / "plugins" / "demo").mkdir(parents=True)
        (project / "demo_plugin.py").write_text(PLUGIN_MODULE, encoding="utf-8")
        (project / "plugins" / "demo" / "atomc-plugin.json").write_text(
            json.dumps(MANIFEST, indent=2), encoding="utf-8"
        )
        state_dir = root / "state"
        port = free_port()
        env = os.environ.copy()
        env.update(
            ATOMCD_STATE_DIR=str(state_dir),
            ATOMCD_HOST="127.0.0.1",
            ATOMCD_PORT=str(port),
            PYTHONPATH=str(project),
        )
        log = (root / "daemon.log").open("w", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, "-m", "atomcd", "serve", "--project", str(project), "--json"],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            _wait_health(base)
            state = json.loads((state_dir / "daemon.json").read_text(encoding="utf-8"))
            print(f"# daemon.json: pid={state['pid']} port={state['port']} token=<redacted>")

            health = httpx.get(f"{base}/health").json()
            print(f"# GET /health -> {json.dumps(health, sort_keys=True)}")
            schema = httpx.get(f"{base}/schema").json()
            print(
                f"# GET /schema -> title={schema['title']} schema_version default="
                f"{schema['properties']['schema_version']['default']}"
            )

            headers = {"Authorization": f"Bearer {state['token']}"}
            collected: list[dict[str, Any]] = []
            with connect(f"ws://127.0.0.1:{port}/rpc", additional_headers=headers) as ws:
                got = rpc(ws, "ir.get", {"path": "/"}, 1, collected)
                print(f"# ir.get / -> rev={got['result']['rev']}")

                tx = rpc(
                    ws,
                    "ir.transact",
                    {
                        "path": "/electrical",
                        "base_rev": 0,
                        "ops": [{"op": "add", "path": "", "value": ELECTRICAL}],
                    },
                    2,
                    collected,
                )
                print(
                    f"# ir.transact /electrical -> new_rev={tx['result']['new_rev']} "
                    f"changed={tx['result']['changed_paths']}"
                )

                conflict = rpc(
                    ws,
                    "ir.transact",
                    {
                        "path": "/electrical",
                        "base_rev": 0,
                        "ops": [{"op": "remove", "path": "/source"}],
                    },
                    3,
                    collected,
                )
                print(
                    f"# stale ir.transact -> error {conflict['error']['code']} "
                    f"{conflict['error']['data']}"
                )

                rpc(
                    ws,
                    "events.subscribe",
                    {"topics": ["gate.result", "dag.node.end"]},
                    4,
                    collected,
                )
                gates = rpc(ws, "gates.run", {"ids": ["gate:demo.ok"]}, 5, collected)
                print(
                    f"# gates.run -> {gates['result'][0]['id']} status="
                    f"{gates['result'][0]['status']}"
                )

                run = rpc(ws, "dag.run", {"targets": ["demo:refresh"], "force": True}, 6, collected)
                print(f"# dag.run -> run_id={run['result']['run_id']}")

                shutdown = rpc(ws, "daemon.shutdown", {}, 7, collected)
                print(f"# daemon.shutdown -> {shutdown['result']}")

            for message in collected:
                print(f"# event <- {message['params']['topic']} {message['params']['data']}")
        finally:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover - demo safety
                proc.terminate()
                proc.wait(timeout=5)
            log.close()

        exists = (state_dir / "daemon.json").exists()
        print(f"# pid file removed after shutdown: {not exists}")
        return 0 if not exists else 1


def _wait_health(base: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base}/health", timeout=1.0).json().get("ok"):
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise SystemExit("daemon did not become healthy")


if __name__ == "__main__":
    raise SystemExit(main())
