"""Shared fixtures: deterministic clock, dummy credentials and a network kill-switch."""

from __future__ import annotations

import socket
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

# CI runs one repository-wide pytest with ``--import-mode=importlib``, which does not put this
# directory on ``sys.path``; expose the local helpers/cassette utilities explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parent))

FIXED_NOW = datetime(2026, 11, 5, 12, 0, 0, tzinfo=UTC)
FIXED_NOW_TEXT = "2026-11-05T12:00:00Z"


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prove the suite never opens a socket; adapters only use injected transports."""

    def deny_connect(self: socket.socket, address: object, *args: object, **kwargs: object) -> None:
        del self, address, args, kwargs
        raise AssertionError("network access is disabled in sourcing tests")

    def deny_create_connection(address: object, *args: object, **kwargs: object) -> None:
        del address, args, kwargs
        raise AssertionError("network access is disabled in sourcing tests")

    monkeypatch.setattr(socket.socket, "connect", deny_connect)
    monkeypatch.setattr(socket, "create_connection", deny_create_connection)


@pytest.fixture
def fixed_clock() -> Callable[[], datetime]:
    def clock() -> datetime:
        return FIXED_NOW

    return clock


@pytest.fixture
def credentials() -> dict[str, dict[str, str]]:
    return {
        "lcsc": {},
        "mouser": {"MOUSER_API_KEY": "test-mouser-key"},
        "digikey": {
            "DIGIKEY_ACCESS_TOKEN": "test-digikey-token",
            "DIGIKEY_CLIENT_ID": "test-digikey-client",
        },
        "nexar": {"NEXAR_ACCESS_TOKEN": "test-nexar-token"},
    }
