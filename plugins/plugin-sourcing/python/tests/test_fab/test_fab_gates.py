"""The ``fab.quote_under_budget`` gate: PASS/FAIL/SKIP/ERROR over IR data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from _sourcing_helpers import FakeContext
from atomc_core_ir import FabQuote
from atomc_plugin_sourcing.fab.gates import (
    check_quote_under_budget,
    evaluate_quote_budget,
    gate_skip_no_quotes,
)
from atomc_plugin_sourcing.fab.spec import DEFAULT_FAB_BUDGET_MINOR

GOLDEN = Path(__file__).with_name("goldens") / "jlcpcb.json"


def pad_quote(total_minor: int | None = None) -> FabQuote:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))["default"]
    if total_minor is not None:
        data["total_minor"] = total_minor
    return FabQuote.model_validate(data)


def fake_context(document: dict[str, Any]) -> FakeContext:
    return FakeContext(ir=document, rev=3, produces=("/sourcing", "/fabrication"))


def test_evaluate_pass_when_cheapest_under_budget() -> None:
    result = evaluate_quote_budget(
        [pad_quote(1116)], 7500, budget_source="project budget /sourcing/budget.total_minor"
    )
    assert result["status"] == "PASS"
    assert result["refs"] == ["quote:jlcpcb_66530c87b0549254"]


def test_evaluate_fail_when_cheapest_over_budget() -> None:
    result = evaluate_quote_budget(
        [pad_quote(8000)], 7500, budget_source="project budget /sourcing/budget.total_minor"
    )
    assert result["status"] == "FAIL"
    breakdown = next(item for item in result["evidence"] if item["kind"] == "json")
    assert breakdown["data"]["cheapest"]["total_minor"] == 8000
    assert breakdown["data"]["budget_minor"] == 7500
    assert breakdown["data"]["cheapest"]["breakdown"] == {"pcb": 216, "shipping": 900}


def test_evaluate_skip_without_quotes() -> None:
    result = evaluate_quote_budget([], 7500, budget_source="x")
    assert result == gate_skip_no_quotes()
    assert result["status"] == "SKIP"
    assert "no quotes fetched yet" in result["summary"]


def test_evaluate_picks_cheapest_across_quotes() -> None:
    result = evaluate_quote_budget([pad_quote(5000), pad_quote(1116)], 2000, budget_source="x")
    assert result["status"] == "PASS"
    breakdown = next(item for item in result["evidence"] if item["kind"] == "json")
    assert breakdown["data"]["cheapest"]["total_minor"] == 1116


async def test_gate_pass_from_ir() -> None:
    document = {
        "sourcing": {"budget": {"per_unit_minor": 1500, "total_minor": 7500}},
        "fabrication": {"_meta": {"rev": 3}, "quotes": [pad_quote().model_dump(mode="json")]},
    }
    result = await check_quote_under_budget(fake_context(document))
    assert result["status"] == "PASS"


async def test_gate_fail_from_ir_reports_breakdown() -> None:
    document = {
        "sourcing": {"budget": {"per_unit_minor": 1500, "total_minor": 500}},
        "fabrication": {"_meta": {"rev": 3}, "quotes": [pad_quote().model_dump(mode="json")]},
    }
    result = await check_quote_under_budget(fake_context(document))
    assert result["status"] == "FAIL"
    json_evidence = [item for item in result["evidence"] if item["kind"] == "json"]
    assert json_evidence
    assert json_evidence[0]["data"]["cheapest"]["total_minor"] == 1116


async def test_gate_skip_when_no_quotes() -> None:
    document = {"fabrication": {"_meta": {"rev": 3}, "quotes": []}}
    result = await check_quote_under_budget(fake_context(document))
    assert result["status"] == "SKIP"
    assert "no quotes fetched yet" in result["summary"]


async def test_gate_skip_when_fabrication_absent() -> None:
    result = await check_quote_under_budget(fake_context({}))
    assert result["status"] == "SKIP"


async def test_gate_uses_documented_default_budget_when_absent() -> None:
    quote = pad_quote(9000).model_dump(mode="json")
    document = {"fabrication": {"_meta": {"rev": 3}, "quotes": [quote]}}
    result = await check_quote_under_budget(fake_context(document))
    assert result["status"] == "PASS"
    assert DEFAULT_FAB_BUDGET_MINOR == 10000
    assert any("documented default" in item["message"] for item in result["evidence"])


async def test_gate_error_on_invalid_quote() -> None:
    document = {"fabrication": {"_meta": {"rev": 3}, "quotes": [{"id": "quote:bad"}]}}
    result = await check_quote_under_budget(fake_context(document))
    assert result["status"] == "ERROR"
