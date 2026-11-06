"""Selection constraints for the pure sourcing optimizer.

The frozen ``Sourcing`` IR model has no constraints field. The ``optimize`` tool therefore takes
constraints in its payload; gates use the documented defaults below unless a caller supplies an
explicit cap. ``vendor_budget_weights`` are positive multipliers applied to a vendor's extended
cost when ranking candidates (default ``1`` for every vendor).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

__all__ = [
    "DEFAULT_LEAD_TIME_CAP_DAYS",
    "SelectionConstraints",
    "SelectionConstraintsError",
]

DEFAULT_LEAD_TIME_CAP_DAYS = 14
"""Documented default maximum chosen lead time.

The frozen IR exposes per-offer lead times but no configured cap. Fourteen days is the maximum
lead time in the atomc-pad example and a common LCSC/JLCPCB turnaround, so gates use it as an
explicit, evidence-carrying default rather than silently passing unknown lead times.
"""


class SelectionConstraintsError(ValueError):
    """Raised when optimizer constraints are malformed."""


@dataclass(frozen=True, slots=True)
class SelectionConstraints:
    """Constraints applied by :func:`atomc_plugin_sourcing.optimizer.select.select_offers`.

    ``lead_time_cap_days=None`` disables the cap explicitly. ``vendor_count_cap`` limits the
    number of distinct vendors across all chosen offers; ``None`` leaves the count unlimited.
    """

    lead_time_cap_days: int | None = DEFAULT_LEAD_TIME_CAP_DAYS
    vendor_count_cap: int | None = None
    vendor_budget_weights: Mapping[str, Decimal] = field(default_factory=dict)

    def __post_init__(self) -> None:
        cap = self.lead_time_cap_days
        if cap is not None and (isinstance(cap, bool) or not isinstance(cap, int) or cap < 0):
            raise SelectionConstraintsError("'lead_time_cap_days' must be a non-negative integer")
        vendor_cap = self.vendor_count_cap
        if vendor_cap is not None and (
            isinstance(vendor_cap, bool) or not isinstance(vendor_cap, int) or vendor_cap < 1
        ):
            raise SelectionConstraintsError("'vendor_count_cap' must be a positive integer")
        normalized: dict[str, Decimal] = {}
        for vendor, raw_weight in self.vendor_budget_weights.items():
            if not isinstance(vendor, str) or not vendor:
                raise SelectionConstraintsError("vendor weight keys must be non-empty strings")
            try:
                weight = raw_weight if isinstance(raw_weight, Decimal) else Decimal(str(raw_weight))
            except (InvalidOperation, ValueError) as exc:
                raise SelectionConstraintsError(
                    f"vendor weight for {vendor!r} must be a positive number"
                ) from exc
            if not weight.is_finite() or weight <= 0:
                raise SelectionConstraintsError(
                    f"vendor weight for {vendor!r} must be a positive number"
                )
            normalized[vendor] = weight
        object.__setattr__(self, "vendor_budget_weights", normalized)

    def weight_for(self, vendor: str) -> Decimal:
        """Return the objective multiplier for ``vendor`` (default ``1``)."""
        return self.vendor_budget_weights.get(vendor, Decimal(1))

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> SelectionConstraints:
        """Parse constraints from an ``optimize`` tool payload object."""
        if raw is None:
            return cls()
        if not isinstance(raw, Mapping):
            raise SelectionConstraintsError("'constraints' must be an object")
        unknown = sorted(
            set(raw) - {"lead_time_cap_days", "vendor_count_cap", "vendor_budget_weights"}
        )
        if unknown:
            raise SelectionConstraintsError(f"unknown constraint key(s): {', '.join(unknown)}")
        weights_raw = raw.get("vendor_budget_weights", {})
        if weights_raw is None:
            weights_raw = {}
        if not isinstance(weights_raw, Mapping):
            raise SelectionConstraintsError("'vendor_budget_weights' must be an object")
        return cls(
            lead_time_cap_days=raw.get("lead_time_cap_days", DEFAULT_LEAD_TIME_CAP_DAYS),
            vendor_count_cap=raw.get("vendor_count_cap"),
            vendor_budget_weights={str(k): v for k, v in weights_raw.items()},
        )
