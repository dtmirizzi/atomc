"""Pure BOM gates: PASS/FAIL/SKIP paths and evidence traceability."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import copy

from _sourcing_helpers import FakeContext
from atomc_plugin_sourcing.optimizer.gates import (
    all_in_stock_gate,
    check_all_in_stock,
    check_cost_under_budget,
    check_lead_time_under_days,
    cost_under_budget_gate,
    lead_time_under_days_gate,
)
from helpers import pad_model, pad_sourcing


def _failed_evidence(result: dict) -> dict:
    for item in result["evidence"]:
        if item["kind"] == "json":
            return item["data"]
    raise AssertionError("expected json evidence")


def test_all_bom_gates_pass_on_pad_fixture() -> None:
    model = pad_model()
    for check in (
        check_all_in_stock(model),
        check_lead_time_under_days(model),
        check_cost_under_budget(model),
    ):
        assert check["status"] == "PASS", check
        assert check["evidence"]


def test_all_in_stock_fails_when_chosen_stock_is_short() -> None:
    node = pad_sourcing()
    node["bom"][0]["offers"][0]["stock"] = 1
    result = check_all_in_stock(node)
    assert result["status"] == "FAIL"
    assert "cannot be covered" in result["summary"]
    failure = _failed_evidence(result)["failures"][0]
    assert failure["line"] == "bom:U1"
    assert "insufficient stock for required quantity" in failure["reason"]
    assert "bom:U1" in result["refs"]


def test_all_in_stock_fails_when_stock_cannot_meet_moq() -> None:
    node = pad_sourcing()
    node["bom"][0]["offers"][0]["stock"] = 5
    node["bom"][0]["offers"][0]["moq"] = 10
    result = check_all_in_stock(node)
    assert result["status"] == "FAIL"
    failure = _failed_evidence(result)["failures"][0]
    assert "insufficient stock for MOQ order quantity" in failure["reason"]
    assert failure["order_qty"] == 10


def test_lead_time_gate_fails_over_cap_and_unknown() -> None:
    over = pad_sourcing()
    over["bom"][2]["offers"][0]["lead_time_days"] = 21
    result = check_lead_time_under_days(over)
    assert result["status"] == "FAIL"
    assert "cannot be verified within 14 day(s)" in result["summary"]
    failure = _failed_evidence(result)["failures"][0]
    assert failure["lead_time_days"] == 21

    unknown = pad_sourcing()
    unknown["bom"][0]["offers"][0]["lead_time_days"] = None
    unknown_result = check_lead_time_under_days(unknown)
    assert unknown_result["status"] == "FAIL"
    assert "lead time unknown" in _failed_evidence(unknown_result)["failures"][0]["reason"]


def test_lead_time_gate_uses_explicit_cap_argument() -> None:
    result = check_lead_time_under_days(pad_model(), cap_days=10)
    assert result["status"] == "FAIL"
    assert _failed_evidence(result)["cap_days"] == 10
    assert _failed_evidence(result)["max_chosen_lead_time_days"] == 14


def test_cost_gate_fails_total_budget_but_reports_per_unit() -> None:
    node = pad_sourcing()
    node["budget"]["total_minor"] = 2000
    result = check_cost_under_budget(node)
    assert result["status"] == "FAIL"
    data = _failed_evidence(result)
    assert data["total_cost_minor"] == 2465
    assert data["per_unit_cost_minor"] == "493"
    assert data["total_budget_minor"] == 2000
    assert data["per_unit_budget_minor"] == 1500
    assert "total 2465 exceeds 2000" in result["summary"]


def test_cost_gate_fails_per_unit_budget_but_reports_total() -> None:
    node = pad_sourcing()
    node["budget"]["per_unit_minor"] = 400
    result = check_cost_under_budget(node)
    assert result["status"] == "FAIL"
    data = _failed_evidence(result)
    assert data["total_cost_minor"] == 2465
    assert data["per_unit_cost_minor"] == "493"
    assert "per unit 493 exceeds 400" in result["summary"]


def test_cost_gate_skips_without_budget_or_bom() -> None:
    no_budget = pad_sourcing()
    del no_budget["budget"]
    assert check_cost_under_budget(no_budget)["status"] == "SKIP"

    empty = pad_sourcing()
    empty["bom"] = []
    assert check_all_in_stock(empty)["status"] == "SKIP"
    assert check_lead_time_under_days(empty)["status"] == "SKIP"
    assert check_cost_under_budget(empty)["status"] == "SKIP"


async def test_gate_handlers_read_ir_and_skip_when_absent() -> None:
    node = pad_sourcing()
    result = await all_in_stock_gate(FakeContext(ir={"sourcing": copy.deepcopy(node)}))
    assert result["status"] == "PASS"

    missing = await cost_under_budget_gate(FakeContext(ir={}))
    assert missing["status"] == "SKIP"
    assert "absent" in missing["summary"]


async def test_gate_handler_returns_error_for_invalid_sourcing() -> None:
    result = await lead_time_under_days_gate(FakeContext(ir={"sourcing": {"bom": []}}))
    assert result["status"] == "ERROR"
    assert "invalid" in result["summary"]
