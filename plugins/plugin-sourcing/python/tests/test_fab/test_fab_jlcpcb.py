"""JLCPCB adapter: request mapping, response normalization and honest failure paths."""

from __future__ import annotations

import json
import pathlib
from collections.abc import Callable
from datetime import datetime

import httpx
import pytest
from atomc_core_ir import Assembly, PcbSpec
from atomc_plugin_sourcing.fab.jlcpcb import (
    COLOR_ENUM,
    FINISH_ENUM,
    JlcpcbAdapter,
    quote_id_for_spec,
)
from atomc_plugin_sourcing.fab.spec import DEFAULT_PCB_SPEC
from test_fab._fab_cassettes import cassette_transport, static_transport

GOLDEN_DIR = pathlib.Path(__file__).with_name("goldens")
FIXED_NOW_TEXT = "2026-11-05T12:00:00Z"

FAB_ENV: dict[str, str] = {"JLCPCB_APP_ID": "test-app", "JLCPCB_ACCESS_KEY": "test-key"}


def cassette_adapter(fixed_clock: Callable[[], datetime]) -> JlcpcbAdapter:
    return JlcpcbAdapter(
        transport=cassette_transport("jlcpcb"),
        env=dict(FAB_ENV),
        clock=fixed_clock,
    )


def _golden(name: str) -> dict[str, object]:
    data = json.loads((GOLDEN_DIR / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_request_body_matches_golden() -> None:
    adapter = JlcpcbAdapter(env=dict(FAB_ENV))
    assembly = Assembly(side="both", parts_count=3)
    golden = _golden("jlcpcb_request.json")
    assert adapter.request_body(DEFAULT_PCB_SPEC) == golden["default"]
    assert adapter.request_body(DEFAULT_PCB_SPEC, assembly) == golden["assembly"]


def test_request_body_maps_enums() -> None:
    adapter = JlcpcbAdapter(env=dict(FAB_ENV))
    spec = PcbSpec(
        layers=4,
        width_mm=100.0,
        height_mm=50.0,
        thickness_mm=1.2,
        finish="ENIG",
        color="Black",
        qty=10,
    )
    body = adapter.request_body(spec)
    assert body["orderType"] == 1
    assert body["pcbParam"]["layer"] == 4
    assert body["pcbParam"]["width"] == 100.0
    assert body["pcbParam"]["length"] == 50.0
    assert body["pcbParam"]["qty"] == 10
    assert body["pcbParam"]["pcbColor"] == COLOR_ENUM["black"]
    assert body["pcbParam"]["surfaceFinish"] == FINISH_ENUM["ENIG"]


def test_response_normalization_matches_golden(fixed_clock: Callable[[], datetime]) -> None:
    adapter = cassette_adapter(fixed_clock)
    result = adapter.quote(DEFAULT_PCB_SPEC)
    assert result.status == "OK"
    assert result.quote is not None
    assert result.quote.model_dump(mode="json") == _golden("jlcpcb.json")["default"]
    assert result.quote.fetched_at.strftime("%Y-%m-%dT%H:%M:%SZ") == FIXED_NOW_TEXT


def test_assembly_quote_includes_assembly_breakdown(
    fixed_clock: Callable[[], datetime],
) -> None:
    adapter = cassette_adapter(fixed_clock)
    result = adapter.quote(DEFAULT_PCB_SPEC, Assembly(side="both", parts_count=3))
    assert result.status == "OK"
    assert result.quote is not None
    assert result.quote.model_dump(mode="json") == _golden("jlcpcb.json")["assembly"]
    assert result.quote.breakdown["assembly"] == 1500


def test_quote_id_is_deterministic_and_spec_sensitive() -> None:
    assert quote_id_for_spec(DEFAULT_PCB_SPEC) == quote_id_for_spec(DEFAULT_PCB_SPEC)
    bigger = DEFAULT_PCB_SPEC.model_copy(update={"qty": 50})
    assert quote_id_for_spec(bigger) != quote_id_for_spec(DEFAULT_PCB_SPEC)


def test_missing_credentials_are_unavailable_without_a_call(
    fixed_clock: Callable[[], datetime],
) -> None:
    adapter = JlcpcbAdapter(transport=static_transport({}), env={}, clock=fixed_clock)
    result = adapter.quote(DEFAULT_PCB_SPEC)
    assert result.status == "UNAVAILABLE"
    assert result.quote is None
    assert "requires credentials" in (result.message or "")
    assert "no live call was made" in (result.message or "")


def test_unreachable_endpoint_is_unavailable(fixed_clock: Callable[[], datetime]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    adapter = JlcpcbAdapter(
        transport=httpx.MockTransport(handler), env=dict(FAB_ENV), clock=fixed_clock
    )
    result = adapter.quote(DEFAULT_PCB_SPEC)
    assert result.status == "UNAVAILABLE"
    assert result.quote is None
    assert "unreachable" in (result.message or "")


def test_rejected_auth_is_unavailable(fixed_clock: Callable[[], datetime]) -> None:
    adapter = JlcpcbAdapter(
        transport=static_transport({"error": "denied"}, status_code=401),
        env=dict(FAB_ENV),
        clock=fixed_clock,
    )
    result = adapter.quote(DEFAULT_PCB_SPEC)
    assert result.status == "UNAVAILABLE"
    assert result.quote is None
    assert "rejected" in (result.message or "")


def test_error_code_is_error_without_a_quote(fixed_clock: Callable[[], datetime]) -> None:
    payload = {"code": 500, "data": None, "message": "System error. Please try again later."}
    adapter = JlcpcbAdapter(
        transport=static_transport(payload), env=dict(FAB_ENV), clock=fixed_clock
    )
    result = adapter.quote(DEFAULT_PCB_SPEC)
    assert result.status == "ERROR"
    assert result.quote is None
    assert "System error" in (result.message or "")


def test_missing_data_is_error_without_a_quote(fixed_clock: Callable[[], datetime]) -> None:
    adapter = JlcpcbAdapter(
        transport=static_transport({"code": 200, "data": None, "message": "success"}),
        env=dict(FAB_ENV),
        clock=fixed_clock,
    )
    result = adapter.quote(DEFAULT_PCB_SPEC)
    assert result.status == "ERROR"
    assert result.quote is None


def test_malformed_price_discards_the_whole_response(
    fixed_clock: Callable[[], datetime],
) -> None:
    payload = {
        "code": 200,
        "data": {
            "price": "not-a-price",
            "currency": "USD",
            "leadTime": "3-5 days",
            "totalPrice": 11.16,
        },
        "message": "success",
    }
    adapter = JlcpcbAdapter(
        transport=static_transport(payload), env=dict(FAB_ENV), clock=fixed_clock
    )
    result = adapter.quote(DEFAULT_PCB_SPEC)
    assert result.status == "ERROR"
    assert result.quote is None
    assert "price" in (result.message or "")


def test_lead_time_range_uses_the_first_number(
    fixed_clock: Callable[[], datetime],
) -> None:
    adapter = cassette_adapter(fixed_clock)
    result = adapter.quote(DEFAULT_PCB_SPEC)
    assert result.quote is not None
    assert result.quote.lead_time_days == 3


def test_auth_header_is_signed_and_present(fixed_clock: Callable[[], datetime]) -> None:
    adapter = JlcpcbAdapter(env=dict(FAB_ENV), clock=fixed_clock)
    headers = adapter.auth_headers('{"orderType":1}')
    assert headers["Content-Type"] == "application/json"
    assert headers["Authorization"].startswith('JOP-HMAC-SHA256 appid="test-app"')
    assert "signature=" in headers["Authorization"]
    # Deterministic for a fixed clock: same body -> same signature.
    assert adapter.auth_headers('{"orderType":1}') == headers


@pytest.mark.parametrize("finish", ["HASL", "LF-HASL", "ENIG"])
def test_all_finishes_map(finish: str) -> None:
    adapter = JlcpcbAdapter(env=dict(FAB_ENV))
    spec = DEFAULT_PCB_SPEC.model_copy(update={"finish": finish})
    assert adapter.request_body(spec)["pcbParam"]["surfaceFinish"] == FINISH_ENUM[finish]
