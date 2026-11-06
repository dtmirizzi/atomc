"""Pure BOM gates over the frozen ``/sourcing`` subtree.

Each ``check_*`` function is a deterministic function of the IR value it receives: no vendor
call, no clock and no filesystem. Handlers read ``/sourcing`` through the plugin context and hand
the validated model to these functions. The daemon fills in the frozen ``GateResult`` metadata.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from atomc_core_ir import BomLine, Offer, Sourcing

from .constraints import DEFAULT_LEAD_TIME_CAP_DAYS
from .ir import read_value

__all__ = [
    "all_in_stock_gate",
    "check_all_in_stock",
    "check_cost_under_budget",
    "check_lead_time_under_days",
    "cost_under_budget_gate",
    "lead_time_under_days_gate",
]


def _text(message: str) -> dict[str, Any]:
    return {"kind": "text", "message": message}


def _json(data: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "json", "data": data}


def _result(
    status: str,
    summary: str,
    *,
    evidence: list[dict[str, Any]] | None = None,
    suggestions: list[dict[str, Any]] | None = None,
    refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "summary": summary,
        "evidence": evidence or [],
        "suggestions": suggestions or [],
        "refs": refs or [],
    }


def _coerce_sourcing(value: Sourcing | Mapping[str, Any]) -> Sourcing:
    if isinstance(value, Sourcing):
        return value
    if isinstance(value, Mapping):
        return Sourcing.model_validate(value)
    raise TypeError(f"expected Sourcing or mapping, got {type(value).__name__}")


def _chosen_offer(line: BomLine) -> tuple[Offer | None, str | None]:
    chosen_ref = line.chosen_offer_ref
    if chosen_ref is None:
        return None, "no chosen offer"
    for offer in line.offers:
        if offer.id == chosen_ref:
            return offer, None
    return None, f"chosen offer {chosen_ref!r} is not present in the line offers"


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def check_all_in_stock(sourcing: Sourcing | Mapping[str, Any]) -> dict[str, Any]:
    """``bom.all_in_stock`` — each chosen offer covers the required quantity and its MOQ."""
    model = _coerce_sourcing(sourcing)
    if not model.bom:
        return _result("SKIP", "no BOM lines to check", evidence=[_text("BOM array is empty")])

    failures: list[dict[str, Any]] = []
    for line in model.bom:
        required = model.build_qty * line.qty_per_unit
        offer, reason = _chosen_offer(line)
        if offer is None:
            failures.append({"line": line.id, "reason": reason})
            continue
        order_qty = max(required, offer.moq)
        if offer.stock < required:
            failures.append(
                {
                    "line": line.id,
                    "chosen_offer_ref": offer.id,
                    "reason": "insufficient stock for required quantity",
                    "required_qty": required,
                    "stock": offer.stock,
                    "moq": offer.moq,
                }
            )
        elif offer.stock < order_qty:
            failures.append(
                {
                    "line": line.id,
                    "chosen_offer_ref": offer.id,
                    "reason": "insufficient stock for MOQ order quantity",
                    "required_qty": required,
                    "order_qty": order_qty,
                    "stock": offer.stock,
                    "moq": offer.moq,
                }
            )

    evidence = [
        _json(
            {
                "bom_lines": len(model.bom),
                "build_qty": model.build_qty,
                "failures": failures,
            }
        )
    ]
    if failures:
        return _result(
            "FAIL",
            f"{len(failures)} BOM line(s) cannot be covered by their chosen offer",
            evidence=evidence,
            suggestions=[
                {"message": "run the sourcing optimize tool or choose another offer in stock"}
            ],
            refs=[str(item["line"]) for item in failures],
        )
    return _result(
        "PASS",
        f"all {len(model.bom)} BOM line(s) have chosen offers covering quantity and MOQ",
        evidence=evidence,
    )


def check_lead_time_under_days(
    sourcing: Sourcing | Mapping[str, Any],
    cap_days: int = DEFAULT_LEAD_TIME_CAP_DAYS,
) -> dict[str, Any]:
    """``bom.lead_time_under_days`` — every chosen offer has a verifiable lead time <= cap."""
    if isinstance(cap_days, bool) or not isinstance(cap_days, int) or cap_days < 0:
        raise ValueError("cap_days must be a non-negative integer")
    model = _coerce_sourcing(sourcing)
    if not model.bom:
        return _result("SKIP", "no BOM lines to check", evidence=[_text("BOM array is empty")])

    failures: list[dict[str, Any]] = []
    measured: list[int] = []
    for line in model.bom:
        offer, reason = _chosen_offer(line)
        if offer is None:
            failures.append({"line": line.id, "reason": reason})
            continue
        lead = offer.lead_time_days
        if lead is None:
            failures.append(
                {
                    "line": line.id,
                    "chosen_offer_ref": offer.id,
                    "reason": "lead time unknown; cannot verify against the cap",
                }
            )
            continue
        measured.append(lead)
        if lead > cap_days:
            failures.append(
                {
                    "line": line.id,
                    "chosen_offer_ref": offer.id,
                    "reason": "lead time exceeds the configured cap",
                    "lead_time_days": lead,
                    "cap_days": cap_days,
                }
            )

    max_lead = max(measured) if measured else None
    evidence = [
        _text(
            "No lead-time cap exists in the frozen /sourcing model; the default "
            f"{DEFAULT_LEAD_TIME_CAP_DAYS} day(s) is documented in optimizer.constraints."
        ),
        _json(
            {
                "cap_days": cap_days,
                "max_chosen_lead_time_days": max_lead,
                "bom_lines": len(model.bom),
                "failures": failures,
            }
        ),
    ]
    if failures:
        return _result(
            "FAIL",
            f"{len(failures)} chosen offer(s) cannot be verified within {cap_days} day(s)",
            evidence=evidence,
            suggestions=[{"message": "choose an offer with a known lead time within the cap"}],
            refs=[str(item["line"]) for item in failures],
        )
    return _result(
        "PASS",
        f"max chosen lead time {max_lead} day(s) is within the {cap_days}-day cap",
        evidence=evidence,
    )


def check_cost_under_budget(sourcing: Sourcing | Mapping[str, Any]) -> dict[str, Any]:
    """``bom.cost_under_budget`` — extended chosen cost within total and per-unit budgets."""
    model = _coerce_sourcing(sourcing)
    if model.budget is None:
        return _result(
            "SKIP",
            "no sourcing budget is configured",
            evidence=[_text("/sourcing has no budget node")],
        )
    if not model.bom:
        return _result("SKIP", "no BOM lines to price", evidence=[_text("BOM array is empty")])

    failures: list[dict[str, Any]] = []
    total_cost = 0
    for line in model.bom:
        offer, reason = _chosen_offer(line)
        if offer is None:
            failures.append({"line": line.id, "reason": reason})
            continue
        if offer.currency != model.currency:
            failures.append(
                {
                    "line": line.id,
                    "chosen_offer_ref": offer.id,
                    "reason": "currency does not match the sourcing currency",
                    "offer_currency": offer.currency,
                    "sourcing_currency": model.currency,
                }
            )
            continue
        if not offer.price_breaks:
            failures.append(
                {
                    "line": line.id,
                    "chosen_offer_ref": offer.id,
                    "reason": "offer has no price breaks",
                }
            )
            continue
        required = model.build_qty * line.qty_per_unit
        order_qty = max(required, offer.moq)
        breaks = sorted(offer.price_breaks, key=lambda item: item.qty)
        applicable = [item for item in breaks if item.qty <= order_qty]
        unit_price = (applicable[-1] if applicable else breaks[0]).unit_price_minor
        total_cost += order_qty * unit_price

    per_unit_cost = Decimal(total_cost) / Decimal(model.build_qty)
    total_limit = model.budget.total_minor
    per_unit_limit = model.budget.per_unit_minor
    total_ok = total_limit is None or total_cost <= total_limit
    per_unit_ok = per_unit_cost <= per_unit_limit
    evidence = [
        _json(
            {
                "total_cost_minor": total_cost,
                "per_unit_cost_minor": _decimal_text(per_unit_cost),
                "total_budget_minor": total_limit,
                "per_unit_budget_minor": per_unit_limit,
                "build_qty": model.build_qty,
                "bom_lines": len(model.bom),
                "failures": failures,
            }
        )
    ]
    if failures:
        return _result(
            "FAIL",
            f"cannot price {len(failures)} chosen offer(s)",
            evidence=evidence,
            suggestions=[{"message": "run the sourcing optimize tool to choose priced offers"}],
            refs=[str(item["line"]) for item in failures],
        )

    total_text = "not configured" if total_limit is None else f"{total_limit} minor"
    summary = (
        f"extended cost {total_cost} minor ({_decimal_text(per_unit_cost)} per unit) vs "
        f"total budget {total_text} and per-unit budget {per_unit_limit} minor"
    )
    if total_ok and per_unit_ok:
        return _result("PASS", summary, evidence=evidence)
    problems: list[str] = []
    if not total_ok:
        problems.append(f"total {total_cost} exceeds {total_limit}")
    if not per_unit_ok:
        problems.append(f"per unit {_decimal_text(per_unit_cost)} exceeds {per_unit_limit}")
    return _result(
        "FAIL",
        summary + "; " + "; ".join(problems),
        evidence=evidence,
        suggestions=[
            {"message": "reduce BOM cost or choose cheaper in-stock offers within budget"}
        ],
        refs=[line.id for line in model.bom],
    )


async def _load_sourcing(ctx: Any) -> tuple[Sourcing | None, str | None]:
    raw = await read_value(ctx, "/sourcing")
    if raw is None:
        return None, "/sourcing is absent"
    try:
        return _coerce_sourcing(raw), None
    except Exception as exc:
        return None, f"/sourcing is invalid: {type(exc).__name__}: {exc}"


async def all_in_stock_gate(ctx: Any) -> dict[str, Any]:
    model, error = await _load_sourcing(ctx)
    if error is not None or model is None:
        return _result("SKIP" if raw_absent(error) else "ERROR", error or "missing /sourcing")
    return check_all_in_stock(model)


async def lead_time_under_days_gate(ctx: Any) -> dict[str, Any]:
    model, error = await _load_sourcing(ctx)
    if error is not None or model is None:
        return _result("SKIP" if raw_absent(error) else "ERROR", error or "missing /sourcing")
    return check_lead_time_under_days(model)


async def cost_under_budget_gate(ctx: Any) -> dict[str, Any]:
    model, error = await _load_sourcing(ctx)
    if error is not None or model is None:
        return _result("SKIP" if raw_absent(error) else "ERROR", error or "missing /sourcing")
    return check_cost_under_budget(model)


def raw_absent(error: str | None) -> bool:
    """True when the read failure means the node simply does not exist."""
    return error == "/sourcing is absent"
