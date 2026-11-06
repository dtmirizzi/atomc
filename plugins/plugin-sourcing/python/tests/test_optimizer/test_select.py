"""Pure selection engine: cost, constraints, vendor caps, ranking and infeasibility."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
from atomc_plugin_sourcing.optimizer.constraints import (
    DEFAULT_LEAD_TIME_CAP_DAYS,
    SelectionConstraints,
    SelectionConstraintsError,
)
from atomc_plugin_sourcing.optimizer.select import select_offers, select_offers_from_mapping
from helpers import bom_line, offer, pad_model, pad_sourcing, sourcing


def test_pad_fixture_golden_selection_keeps_existing_choices() -> None:
    model = pad_model()
    result = select_offers(model)

    assert [line.chosen_offer_ref for line in result.lines] == [
        "offer:U1_lcsc",
        "offer:U2_lcsc",
        "offer:J1_lcsc",
    ]
    # 5 x 390 (U1 price break) + 5 x 8 + 5 x 95 = 2465 minor units.
    assert result.total_extended_cost_minor == 2465
    assert result.distinct_vendors == ("lcsc",)
    assert all(line.feasible for line in result.lines)
    assert all(line.alternates == () for line in result.lines)
    assert result.constraints.lead_time_cap_days == DEFAULT_LEAD_TIME_CAP_DAYS


def test_select_offers_from_raw_mapping_matches_pad_fixture() -> None:
    result = select_offers_from_mapping(pad_sourcing())
    assert [line.chosen_offer_ref for line in result.lines] == [
        "offer:U1_lcsc",
        "offer:U2_lcsc",
        "offer:J1_lcsc",
    ]


def test_cheapest_feasible_offer_wins_and_alternates_are_ranked() -> None:
    line = bom_line(
        offers=[
            offer("offer:slow", stock=20, unit_price_minor=90),
            offer("offer:cheap", vendor="mouser", stock=20, unit_price_minor=80),
        ],
        qty_per_unit=2,
    )
    result = select_offers(sourcing([line], build_qty=2))

    selected = result.lines[0]
    assert selected.chosen_offer_ref == "offer:cheap"
    assert selected.order_qty == 4
    assert selected.unit_price_minor == 80
    assert selected.extended_cost_minor == 320
    assert selected.ranked_offer_refs == ("offer:cheap", "offer:slow")
    assert len(selected.alternates) == 1
    assert "rank 2" in (selected.alternates[0].reason or "")
    assert "offer=offer:slow" in (selected.alternates[0].reason or "")
    assert selected.alternates[0].lcsc == "slow"


def test_tie_break_prefers_higher_stock_then_sku() -> None:
    stock_tie = bom_line(
        offers=[
            offer("offer:a", sku="A", stock=10, unit_price_minor=100),
            offer("offer:b", sku="B", stock=20, unit_price_minor=100),
        ],
        qty_per_unit=2,
    )
    assert select_offers(sourcing([stock_tie], build_qty=2)).lines[0].chosen_offer_ref == "offer:b"

    sku_tie = bom_line(
        offers=[
            offer("offer:z", sku="Z", stock=20, unit_price_minor=100),
            offer("offer:a", sku="A", stock=20, unit_price_minor=100),
        ],
        qty_per_unit=2,
    )
    assert select_offers(sourcing([sku_tie], build_qty=2)).lines[0].chosen_offer_ref == "offer:a"


def test_lead_time_cap_rejects_unknown_and_late_offers() -> None:
    late = bom_line(offers=[offer("offer:late", lead_time_days=20)])
    result = select_offers(sourcing([late], build_qty=2))
    assert result.lines[0].chosen_offer_ref is None
    assert any(
        "lead time 20 day(s) exceeds cap 14 day(s)" in reason for reason in result.lines[0].reasons
    )

    unknown = bom_line(offers=[offer("offer:unknown", lead_time_days=None)])
    unknown_result = select_offers(sourcing([unknown], build_qty=2))
    assert unknown_result.lines[0].chosen_offer_ref is None
    assert any("lead time unknown" in reason for reason in unknown_result.lines[0].reasons)

    uncapped = select_offers(
        sourcing([late], build_qty=2),
        SelectionConstraints(lead_time_cap_days=None),
    )
    assert uncapped.lines[0].chosen_offer_ref == "offer:late"


def test_stock_and_moq_violations_produce_explicit_reasons() -> None:
    short_stock = bom_line(offers=[offer("offer:short", stock=3)], qty_per_unit=2)
    stock_result = select_offers(sourcing([short_stock], build_qty=2))
    assert stock_result.lines[0].chosen_offer_ref is None
    assert any(
        "stock 3 below required quantity 4" in reason for reason in stock_result.lines[0].reasons
    )

    short_for_moq = bom_line(
        offers=[offer("offer:moq", stock=8, moq=10)],
        qty_per_unit=2,
    )
    moq_result = select_offers(sourcing([short_for_moq], build_qty=2))
    assert moq_result.lines[0].chosen_offer_ref is None
    assert any(
        "stock 8 below MOQ order quantity 10" in reason for reason in moq_result.lines[0].reasons
    )


def test_no_offers_is_infeasible_with_reason() -> None:
    result = select_offers(sourcing([bom_line()], build_qty=2))
    assert result.lines[0].chosen_offer_ref is None
    assert result.lines[0].reasons == ("BOM line has no offers",)
    assert result.infeasible_lines == result.lines


def test_vendor_count_cap_selects_cheapest_single_vendor_subset() -> None:
    line_one = bom_line(
        "bom:U1",
        offers=[
            offer("offer:l1_lcsc", vendor="lcsc", unit_price_minor=10),
            offer("offer:l1_mouser", vendor="mouser", unit_price_minor=11),
        ],
    )
    line_two = bom_line(
        "bom:U2",
        offers=[
            offer("offer:l2_lcsc", vendor="lcsc", unit_price_minor=20),
            offer("offer:l2_mouser", vendor="mouser", unit_price_minor=5),
        ],
    )
    model = sourcing([line_one, line_two], build_qty=1)

    uncapped = select_offers(model)
    assert uncapped.distinct_vendors == ("lcsc", "mouser")
    assert uncapped.total_extended_cost_minor == 15

    capped = select_offers(model, SelectionConstraints(vendor_count_cap=1))
    assert capped.distinct_vendors == ("mouser",)
    assert [line.chosen_offer_ref for line in capped.lines] == [
        "offer:l1_mouser",
        "offer:l2_mouser",
    ]
    assert capped.total_extended_cost_minor == 16


def test_vendor_budget_weight_changes_objective_not_actual_cost() -> None:
    line = bom_line(
        offers=[
            offer("offer:lcsc", vendor="lcsc", unit_price_minor=10),
            offer("offer:mouser", vendor="mouser", unit_price_minor=8),
        ]
    )
    model = sourcing([line], build_qty=1)

    unweighted = select_offers(model)
    assert unweighted.lines[0].chosen_offer_ref == "offer:mouser"
    assert unweighted.total_extended_cost_minor == 8

    weighted = select_offers(
        model,
        SelectionConstraints(vendor_budget_weights={"mouser": "2"}),
    )
    assert weighted.lines[0].chosen_offer_ref == "offer:lcsc"
    assert weighted.total_extended_cost_minor == 10


def test_currency_mismatch_is_infeasible() -> None:
    line = bom_line(offers=[offer("offer:eur", currency="EUR")])
    result = select_offers(sourcing([line], build_qty=2))
    assert result.lines[0].chosen_offer_ref is None
    assert any(
        "currency EUR does not match sourcing currency USD" in reason
        for reason in result.lines[0].reasons
    )


def test_invalid_constraints_are_rejected() -> None:
    with pytest.raises(SelectionConstraintsError, match="unknown constraint key"):
        SelectionConstraints.from_mapping({"unknown": 1})
    with pytest.raises(SelectionConstraintsError, match="positive integer"):
        SelectionConstraints(vendor_count_cap=0)
    with pytest.raises(SelectionConstraintsError, match="positive number"):
        SelectionConstraints(vendor_budget_weights={"lcsc": "0"})
