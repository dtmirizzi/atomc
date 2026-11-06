"""Pure offer selection and BOM gates for the sourcing plugin.

The optimizer never calls a vendor: it consumes the frozen ``/sourcing`` subtree, chooses the
cheapest feasible offer per BOM line under explicit constraints, and reports infeasible lines
with reasons. Gate handlers read the same subtree and evaluate the chosen offers only.
"""

from __future__ import annotations

from .constraints import (
    DEFAULT_LEAD_TIME_CAP_DAYS,
    SelectionConstraints,
    SelectionConstraintsError,
)
from .gates import (
    all_in_stock_gate,
    check_all_in_stock,
    check_cost_under_budget,
    check_lead_time_under_days,
    cost_under_budget_gate,
    lead_time_under_days_gate,
)
from .select import (
    Candidate,
    LineSelection,
    SelectionResult,
    select_offers,
    select_offers_from_mapping,
)
from .tools import optimize_payload

__all__ = [
    "DEFAULT_LEAD_TIME_CAP_DAYS",
    "Candidate",
    "LineSelection",
    "SelectionConstraints",
    "SelectionConstraintsError",
    "SelectionResult",
    "all_in_stock_gate",
    "check_all_in_stock",
    "check_cost_under_budget",
    "check_lead_time_under_days",
    "cost_under_budget_gate",
    "lead_time_under_days_gate",
    "optimize_payload",
    "select_offers",
    "select_offers_from_mapping",
]
