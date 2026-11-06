"""Replay synthetic JLCPCB fabrication cassettes through an injected httpx transport."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

CASSETTE_ROOT = Path(__file__).parent / "cassettes"
GOLDEN_ROOT = Path(__file__).parent / "goldens"


def load_cassettes(fab: str) -> list[dict[str, Any]]:
    directory = CASSETTE_ROOT / fab
    cassettes: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        cassettes.append(json.loads(path.read_text(encoding="utf-8")))
    return cassettes


def cassette_transport(fab: str) -> httpx.MockTransport:
    """Match requests to synthetic cassettes; unmatched requests fail like a dead network."""
    cassettes = load_cassettes(fab)

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode("utf-8")
        for cassette in cassettes:
            match = cassette["request"]
            if request.method != match["method"] or request.url.path != match["path"]:
                continue
            contains = match.get("body_contains")
            if contains and contains not in body:
                continue
            response = cassette["response"]
            return httpx.Response(response.get("status_code", 200), json=response["json"])
        raise httpx.ConnectError(f"no synthetic cassette for {request.method} {request.url}")

    return httpx.MockTransport(handler)


def recording_transport(
    payload: Any,
    *,
    status_code: int = 200,
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    """Return a transport that records requests and always answers with ``payload``."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status_code, json=payload)

    return httpx.MockTransport(handler), requests


def static_transport(payload: Any, *, status_code: int = 200) -> httpx.MockTransport:
    """Return one fixed JSON document for every request."""

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(status_code, json=payload)

    return httpx.MockTransport(handler)


def load_golden(name: str) -> Any:
    return json.loads((GOLDEN_ROOT / f"{name}.json").read_text(encoding="utf-8"))
