"""HTTP endpoints: health and JSON Schema."""

from __future__ import annotations

from atomcd.app import Services
from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["version"] == "0.0.1"
    assert body["ir_rev"] == 0


def test_health_reports_ir_rev(client: TestClient, services: Services) -> None:
    ir = services.store.snapshot
    ir.meta.rev = 7
    services.store._ir = ir
    assert client.get("/health").json()["ir_rev"] == 7


def test_schema(client: TestClient) -> None:
    response = client.get("/schema")
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "SystemIR"
    assert body["properties"]["schema_version"]["default"] == "0.1.0"


def test_openapi_available(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "atomcd"
