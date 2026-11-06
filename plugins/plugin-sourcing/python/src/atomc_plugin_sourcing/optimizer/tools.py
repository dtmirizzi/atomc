"""The ``sourcing:optimize`` tool: choose offers and write the selection into ``/sourcing``.

The tool is pure with respect to external systems: it only reads and writes IR through the plugin
context. No vendor is contacted. Infeasible lines are written with ``chosen_offer_ref: null`` and
their reasons are reported, so a stale or silent best-effort choice cannot survive a run.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from atomc_core_ir import Sourcing

from .constraints import SelectionConstraints, SelectionConstraintsError
from .ir import maybe_await, read_node
from .select import SelectionResult, select_offers

__all__ = ["optimize_payload"]


def _tool_error(message: str) -> dict[str, Any]:
    return {
        "status": "ERROR",
        "available": False,
        "summary": message,
        "evidence": [{"kind": "text", "message": message}],
    }


def _line_report(result: SelectionResult) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for line in result.lines:
        reports.append(
            {
                "line": line.line_id,
                "chosen_offer_ref": line.chosen_offer_ref,
                "vendor": line.chosen_vendor,
                "required_qty": line.required_qty,
                "order_qty": line.order_qty,
                "unit_price_minor": line.unit_price_minor,
                "extended_cost_minor": line.extended_cost_minor,
                "lead_time_days": line.lead_time_days,
                "feasible": line.feasible,
                "reasons": list(line.reasons),
                "ranked_offer_refs": list(line.ranked_offer_refs),
                "alternates": [alternate.model_dump(mode="json") for alternate in line.alternates],
            }
        )
    return reports


def _selection_ops(result: SelectionResult) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []
    for index, line in enumerate(result.lines):
        ops.append(
            {
                "op": "add",
                "path": f"/bom/{index}/chosen_offer_ref",
                "value": line.chosen_offer_ref,
            }
        )
        ops.append(
            {
                "op": "add",
                "path": f"/bom/{index}/alternates",
                "value": [alternate.model_dump(mode="json") for alternate in line.alternates],
            }
        )
    return ops


async def optimize_payload(ctx: Any, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Implementation of the mutating ``optimize`` tool."""
    args: Mapping[str, Any] = payload if payload is not None else {}
    if not isinstance(args, Mapping):
        return _tool_error("tool payload must be an object")

    try:
        constraints = SelectionConstraints.from_mapping(args.get("constraints"))
    except SelectionConstraintsError as exc:
        return _tool_error(str(exc))

    dry_run = args.get("dry_run", False)
    if not isinstance(dry_run, bool):
        return _tool_error("'dry_run' must be a boolean")

    rev, raw = await read_node(ctx, "/sourcing")
    if raw is None:
        return {
            "status": "SKIP",
            "available": False,
            "summary": "/sourcing is absent; nothing to optimize",
            "evidence": [{"kind": "text", "message": "no /sourcing node was read"}],
        }
    try:
        sourcing = raw if isinstance(raw, Sourcing) else Sourcing.model_validate(raw)
    except Exception as exc:
        return _tool_error(f"/sourcing is invalid: {type(exc).__name__}: {exc}")
    if not sourcing.bom:
        return {
            "status": "SKIP",
            "available": False,
            "summary": "/sourcing has no BOM lines; nothing to optimize",
            "evidence": [{"kind": "text", "message": "expected /sourcing/bom to be non-empty"}],
        }

    result = select_offers(sourcing, constraints)
    ops = _selection_ops(result)
    new_rev: Any = None
    if not dry_run:
        try:
            outcome = await maybe_await(ctx.ir_transact("/sourcing", rev, ops))
        except Exception as exc:
            return _tool_error(f"could not write the selection: {type(exc).__name__}: {exc}")
        new_rev = getattr(outcome, "new_rev", None)
        if new_rev is None and isinstance(outcome, Mapping):
            new_rev = outcome.get("new_rev")

    feasible = [line for line in result.lines if line.feasible]
    infeasible = [line for line in result.lines if not line.feasible]
    summary = (
        f"selected {len(feasible)} of {len(result.lines)} BOM line(s); "
        f"extended cost {result.total_extended_cost_minor} minor; "
        f"{len(infeasible)} infeasible"
    )
    if dry_run:
        summary = "dry run: " + summary + "; /sourcing was not written"
    return {
        "status": "OK" if dry_run else "UPDATED",
        "available": bool(feasible),
        "summary": summary,
        "dry_run": dry_run,
        "new_rev": new_rev,
        "selected_lines": len(feasible),
        "infeasible_lines": len(infeasible),
        "total_extended_cost_minor": result.total_extended_cost_minor,
        "distinct_vendors": list(result.distinct_vendors),
        "constraints": {
            "lead_time_cap_days": result.constraints.lead_time_cap_days,
            "vendor_count_cap": result.constraints.vendor_count_cap,
            "vendor_budget_weights": {
                vendor: format(weight.normalize(), "f")
                for vendor, weight in result.constraints.vendor_budget_weights.items()
            },
        },
        "lines": _line_report(result),
    }
