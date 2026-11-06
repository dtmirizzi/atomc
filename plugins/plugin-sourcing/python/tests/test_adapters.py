"""Adapter parsing, credential honesty and malformed-response tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from _sourcing_cassettes import cassette_transport, static_transport
from atomc_plugin_sourcing.adapters import build_adapters
from atomc_plugin_sourcing.adapters.digikey import DigiKeyAdapter
from atomc_plugin_sourcing.adapters.lcsc import LcscAdapter
from atomc_plugin_sourcing.adapters.mouser import MouserAdapter
from atomc_plugin_sourcing.adapters.nexar import NexarAdapter
from atomc_plugin_sourcing.models import ComponentQuery
from conftest import FIXED_NOW_TEXT

ADAPTERS = {
    "lcsc": LcscAdapter,
    "mouser": MouserAdapter,
    "digikey": DigiKeyAdapter,
    "nexar": NexarAdapter,
}

PARTS = {
    "lcsc": ["C60442", "C51118", "C165948"],
    "mouser": ["C60442", "C51118", "C165948"],
    "digikey": ["C60442", "C51118", "C165948"],
    "nexar": ["C60442", "C51118", "C165948"],
}
MPNS = {
    "C60442": "STM32F411CEU6",
    "C51118": "AP2112K-3.3TRG1",
    "C165948": "USB4085-GF-A",
}


def adapter_for(
    vendor: str,
    credentials: dict[str, dict[str, str]],
    fixed_clock: Callable[[], datetime],
    *,
    transport: httpx.BaseTransport | None = None,
) -> Any:
    return ADAPTERS[vendor](
        transport=transport or cassette_transport(vendor),
        env=credentials[vendor],
        clock=fixed_clock,
    )


def query_for(vendor: str, part: str) -> ComponentQuery:
    if vendor == "lcsc":
        return ComponentQuery(lcsc=part)
    return ComponentQuery(mpn=MPNS[part])


@pytest.mark.parametrize("vendor", sorted(ADAPTERS))
@pytest.mark.parametrize("part", PARTS["lcsc"])
def test_adapter_normalization_golden(
    vendor: str,
    part: str,
    credentials: dict[str, dict[str, str]],
    fixed_clock: Callable[[], datetime],
) -> None:
    adapter = adapter_for(vendor, credentials, fixed_clock)
    result = adapter.query(query_for(vendor, part))
    assert result.status == "OK", result
    assert result.cached is False
    golden_path = Path(__file__).parent / "goldens" / f"{vendor}.json"
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    assert [offer.to_dict() for offer in result.offers] == golden[part]
    assert all(offer.to_dict()["fetched_at"] == FIXED_NOW_TEXT for offer in result.offers)


@pytest.mark.parametrize(
    ("vendor", "adapter_cls"),
    [
        ("mouser", MouserAdapter),
        ("digikey", DigiKeyAdapter),
        ("nexar", NexarAdapter),
    ],
)
def test_missing_credentials_are_unavailable_without_offers(
    vendor: str,
    adapter_cls: type,
    fixed_clock: Callable[[], datetime],
) -> None:
    adapter = adapter_cls(transport=static_transport({}), env={}, clock=fixed_clock)
    result = adapter.query(ComponentQuery(mpn="STM32F411CEU6"))
    assert result.status == "UNAVAILABLE"
    assert result.offers == ()
    assert "requires credentials" in (result.message or "")
    assert "no live call was made" in (result.message or "")


def test_lcsc_unreachable_endpoint_is_unavailable(fixed_clock: Callable[[], datetime]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    adapter = LcscAdapter(transport=httpx.MockTransport(handler), env={}, clock=fixed_clock)
    result = adapter.query(ComponentQuery(lcsc="C60442"))
    assert result.status == "UNAVAILABLE"
    assert result.offers == ()
    assert "unreachable" in (result.message or "")


def test_lcsc_rejected_auth_is_unavailable(fixed_clock: Callable[[], datetime]) -> None:
    adapter = LcscAdapter(
        transport=static_transport({"error": "denied"}, status_code=401),
        env={},
        clock=fixed_clock,
    )
    result = adapter.query(ComponentQuery(lcsc="C60442"))
    assert result.status == "UNAVAILABLE"
    assert result.offers == ()
    assert "rejected" in (result.message or "")


def test_malformed_lcsc_response_is_error_without_partial_offers(
    fixed_clock: Callable[[], datetime],
) -> None:
    payload = {
        "code": 200,
        "result": {
            "productCode": "C60442",
            "productModel": "STM32F411CEU6",
            "stockNumber": "lots",
            "priceBreaks": [{"quantity": 1, "price": 0.42}],
        },
    }
    adapter = LcscAdapter(transport=static_transport(payload), env={}, clock=fixed_clock)
    result = adapter.query(ComponentQuery(lcsc="C60442"))
    assert result.status == "ERROR"
    assert result.offers == ()
    assert "stockNumber" in (result.message or "")


def test_one_malformed_part_discards_the_whole_vendor_response(
    fixed_clock: Callable[[], datetime],
) -> None:
    payload = {
        "Errors": [],
        "SearchResults": {
            "Parts": [
                {
                    "ManufacturerPartNumber": "STM32F411CEU6",
                    "MouserPartNumber": "511-STM32F411CEU6",
                    "Availability": "320 In Stock",
                    "PriceBreaks": [{"Quantity": 1, "Price": "$0.45"}],
                },
                {
                    "ManufacturerPartNumber": "BROKEN",
                    "MouserPartNumber": "broken",
                    "Availability": "not a number",
                    "PriceBreaks": [],
                },
            ]
        },
    }
    adapter = MouserAdapter(
        transport=static_transport(payload),
        env={"MOUSER_API_KEY": "key"},
        clock=fixed_clock,
    )
    result = adapter.query(ComponentQuery(mpn="STM32F411CEU6"))
    assert result.status == "ERROR"
    assert result.offers == ()


def test_mouser_api_errors_are_error(fixed_clock: Callable[[], datetime]) -> None:
    adapter = MouserAdapter(
        transport=static_transport({"Errors": ["Invalid API key"], "SearchResults": {}}),
        env={"MOUSER_API_KEY": "key"},
        clock=fixed_clock,
    )
    result = adapter.query(ComponentQuery(mpn="STM32F411CEU6"))
    assert result.status == "ERROR"
    assert result.offers == ()
    assert "Invalid API key" in (result.message or "")


def test_nexar_graphql_errors_are_error(fixed_clock: Callable[[], datetime]) -> None:
    adapter = NexarAdapter(
        transport=static_transport({"Errors": [{"message": "bad query"}]}),
        env={"NEXAR_ACCESS_TOKEN": "token"},
        clock=fixed_clock,
    )
    result = adapter.query(ComponentQuery(mpn="STM32F411CEU6"))
    assert result.status == "ERROR"
    assert result.offers == ()


def test_digikey_requires_mpn_for_lcsc_only_query(
    fixed_clock: Callable[[], datetime],
) -> None:
    adapter = DigiKeyAdapter(
        transport=static_transport({}),
        env={"DIGIKEY_ACCESS_TOKEN": "token"},
        clock=fixed_clock,
    )
    result = adapter.query(ComponentQuery(lcsc="C60442"))
    assert result.status == "UNAVAILABLE"
    assert result.offers == ()


def test_build_adapters_exposes_every_supported_vendor(
    credentials: dict[str, dict[str, str]],
    fixed_clock: Callable[[], datetime],
) -> None:
    adapters = build_adapters(
        env=credentials["lcsc"], transport=static_transport({}), clock=fixed_clock
    )
    assert set(adapters) == set(ADAPTERS)
