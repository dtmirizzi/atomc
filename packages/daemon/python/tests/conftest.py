from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from atomcd.app import Services, create_app
from atomcd.config import DaemonConfig
from atomcd.events import EventBus
from atomcd.ir_store import IRStore
from atomcd.runtime import RuntimeState
from fastapi.testclient import TestClient

TEST_TOKEN = "test-token-1234567890"


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    return root


@pytest.fixture
def config(project_root: Path, tmp_path: Path) -> DaemonConfig:
    return DaemonConfig(
        host="127.0.0.1",
        port=7437,
        project_root=project_root,
        state_dir=tmp_path / "state",
        token=TEST_TOKEN,
    )


@pytest.fixture
def services(config: DaemonConfig) -> Services:
    runtime = RuntimeState(config.state_dir)
    store = IRStore(config.project_root)
    store.load()
    runtime.write(
        pid=12345,
        host=config.host,
        port=config.port,
        token=TEST_TOKEN,
        project_root=str(config.project_root),
        version="0.0.1",
        started_at="2026-11-04T00:00:00Z",
    )
    return Services(
        config=config,
        store=store,
        runtime_state=runtime,
        events=EventBus(),
        version="0.0.1",
    )


@pytest.fixture
def client(services: Services) -> Iterator[TestClient]:
    with TestClient(create_app(services)) as test_client:
        yield test_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_TOKEN}"}
