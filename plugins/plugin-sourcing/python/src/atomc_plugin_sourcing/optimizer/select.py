"""Deterministic offer selection for the frozen ``/sourcing`` subtree.

The optimizer is pure: it consumes BOM lines, offers, budget metadata and explicit constraints,
then returns the chosen offer id and ranked alternates per line. It never calls a vendor and
never invents an offer. Infeasible lines keep ``chosen_offer_ref=None`` and carry explicit
reasons instead of a silent best-effort pick.

Ranking and tie-breaking
------------------------
Candidates are ranked by ``(effective extended cost, -stock, vendor, sku, offer id)``. The
effective cost is the actual extended cost multiplied by the optional per-vendor budget weight.
When a vendor-count cap is configured, every vendor subset up to the cap is enumerated and the
subset minimizing total effective cost wins; ties prefer fewer vendors and then lexicographic
vendor names. With no cap each line independently picks its cheapest feasible candidate.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations
from typing import Any

from atomc_core_ir import Alternate, BomLine, Offer, PriceBreak, Sourcing

from .constraints import SelectionConstraints, SelectionConstraintsError

__all__ = [
    "Candidate",
    "LineSelection",
    "SelectionResult",
    "select_offers",
    "select_offers_from_mapping",
]

_LCSC_VENDORS = frozenset({"lcsc", "jlcpcb"})


@dataclass(frozen=True, slots=True)
class Candidate:
    """One feasible offer for one BOM line, with its order quantity and cost."""

    offer: Offer
    order_qty: int
    unit_price_minor: int
    extended_cost_minor: int
    effective_cost: Decimal
    rank_key: tuple[Decimal, int, str, str, str]


@dataclass(frozen=True, slots=True)
class LineSelection:
    """Selection outcome for one BOM line."""

    line_id: str
    required_qty: int
    order_qty: int | None
    chosen_offer_ref: str | None
    chosen_vendor: str | None
    unit_price_minor: int | None
    extended_cost_minor: int | None
    lead_time_days: int | None
    alternates: tuple[Alternate, ...]
    ranked_offer_refs: tuple[str, ...]
    feasible: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SelectionResult:
    """Whole-BOM selection outcome."""

    lines: tuple[LineSelection, ...]
    total_extended_cost_minor: int
    distinct_vendors: tuple[str, ...]
    constraints: SelectionConstraints

    @property
    def chosen_offer_refs(self) -> tuple[str, ...]:
        return tuple(
            line.chosen_offer_ref for line in self.lines if line.chosen_offer_ref is not None
        )

    @property
    def infeasible_lines(self) -> tuple[LineSelection, ...]:
        return tuple(line for line in self.lines if not line.feasible)


def _unit_price_minor(offer: Offer, order_qty: int) -> int:
    """Return the price-break unit price applying at ``order_qty``.

    The largest break quantity not exceeding ``order_qty`` applies. If every break starts above
    the order quantity (unusual but allowed by the frozen model), the smallest break is used as
    the base price.
    """
    breaks = sorted(offer.price_breaks, key=lambda item: item.qty)
    applicable = [item for item in breaks if item.qty <= order_qty]
    selected: PriceBreak = applicable[-1] if applicable else breaks[0]
    return selected.unit_price_minor


def _candidate_for(
    line: BomLine,
    offer: Offer,
    *,
    build_qty: int,
    constraints: SelectionConstraints,
    sourcing_currency: str,
) -> tuple[Candidate | None, tuple[str, ...]]:
    required_qty = build_qty * line.qty_per_unit
    order_qty = max(required_qty, offer.moq)
    reasons: list[str] = []
    if offer.currency != sourcing_currency:
        reasons.append(
            f"currency {offer.currency} does not match sourcing currency {sourcing_currency}"
        )
    if not offer.price_breaks:
        reasons.append("offer has no price breaks")
    if offer.stock < required_qty:
        reasons.append(
            f"stock {offer.stock} below required quantity {required_qty} "
            f"(build_qty {build_qty} x qty_per_unit {line.qty_per_unit})"
        )
    elif offer.stock < order_qty:
        reasons.append(
            f"stock {offer.stock} below MOQ order quantity {order_qty} "
            f"(MOQ {offer.moq}, required {required_qty})"
        )
    cap = constraints.lead_time_cap_days
    if cap is not None:
        if offer.lead_time_days is None:
            reasons.append(f"lead time unknown; cannot verify <= {cap} day(s)")
        elif offer.lead_time_days > cap:
            reasons.append(f"lead time {offer.lead_time_days} day(s) exceeds cap {cap} day(s)")
    if reasons:
        return None, tuple(reasons)
    unit_price = _unit_price_minor(offer, order_qty)
    extended = order_qty * unit_price
    effective = Decimal(extended) * constraints.weight_for(offer.vendor)
    rank_key = (effective, -offer.stock, offer.vendor, offer.sku, offer.id)
    return (
        Candidate(
            offer=offer,
            order_qty=order_qty,
            unit_price_minor=unit_price,
            extended_cost_minor=extended,
            effective_cost=effective,
            rank_key=rank_key,
        ),
        (),
    )


def _alternate(line: BomLine, candidate: Candidate, rank: int) -> Alternate:
    offer = candidate.offer
    reason = (
        f"rank {rank}; offer={offer.id}; vendor={offer.vendor}; sku={offer.sku}; "
        f"order_qty={candidate.order_qty}; unit_price_minor={candidate.unit_price_minor}; "
        f"extended_minor={candidate.extended_cost_minor}; "
        f"lead_time_days={offer.lead_time_days}; stock={offer.stock}"
    )
    return Alternate(
        mpn=line.mpn or offer.sku,
        lcsc=offer.sku if offer.vendor in _LCSC_VENDORS else line.lcsc,
        reason=reason,
    )


def _ranked_alternates(
    line: BomLine, candidates: list[Candidate], chosen_id: str | None
) -> tuple[Alternate, ...]:
    alternates: list[Alternate] = []
    for rank, candidate in enumerate(candidates, start=1):
        if candidate.offer.id == chosen_id:
            continue
        alternates.append(_alternate(line, candidate, rank))
    return tuple(alternates)


def _line_selection(
    line: BomLine,
    *,
    build_qty: int,
    candidates: list[Candidate],
    chosen: Candidate | None,
    reasons: Iterable[str],
) -> LineSelection:
    chosen_id = chosen.offer.id if chosen is not None else None
    return LineSelection(
        line_id=line.id,
        required_qty=build_qty * line.qty_per_unit,
        order_qty=chosen.order_qty if chosen is not None else None,
        chosen_offer_ref=chosen_id,
        chosen_vendor=chosen.offer.vendor if chosen is not None else None,
        unit_price_minor=chosen.unit_price_minor if chosen is not None else None,
        extended_cost_minor=chosen.extended_cost_minor if chosen is not None else None,
        lead_time_days=chosen.offer.lead_time_days if chosen is not None else None,
        alternates=_ranked_alternates(line, candidates, chosen_id),
        ranked_offer_refs=tuple(candidate.offer.id for candidate in candidates),
        feasible=chosen is not None,
        reasons=() if chosen is not None else tuple(reasons),
    )


def _candidates_by_line(
    sourcing: Sourcing,
    constraints: SelectionConstraints,
) -> tuple[dict[int, list[Candidate]], dict[int, tuple[str, ...]]]:
    candidates: dict[int, list[Candidate]] = {}
    failures: dict[int, tuple[str, ...]] = {}
    for index, line in enumerate(sourcing.bom):
        line_candidates: list[Candidate] = []
        line_failures: list[str] = []
        if not line.offers:
            line_failures.append("BOM line has no offers")
        for offer in line.offers:
            candidate, reasons = _candidate_for(
                line,
                offer,
                build_qty=sourcing.build_qty,
                constraints=constraints,
                sourcing_currency=sourcing.currency,
            )
            if candidate is None:
                line_failures.extend(f"{offer.id}: {reason}" for reason in reasons)
            else:
                line_candidates.append(candidate)
        line_candidates.sort(key=lambda candidate: candidate.rank_key)
        candidates[index] = line_candidates
        failures[index] = tuple(line_failures)
    return candidates, failures


def _select_without_cap(
    bom: list[BomLine],
    candidates: dict[int, list[Candidate]],
    failures: dict[int, tuple[str, ...]],
) -> dict[int, Candidate | None]:
    choices: dict[int, Candidate | None] = {}
    for index in range(len(bom)):
        choices[index] = candidates[index][0] if candidates[index] else None
    return choices


def _select_with_cap(
    bom: list[BomLine],
    candidates: dict[int, list[Candidate]],
    failures: dict[int, tuple[str, ...]],
    cap: int,
) -> tuple[dict[int, Candidate | None], tuple[str, ...]]:
    vendors = sorted(
        {candidate.offer.vendor for items in candidates.values() for candidate in items}
    )
    subsets: list[tuple[str, ...]] = []
    for size in range(1, min(cap, len(vendors)) + 1):
        subsets.extend(tuple(subset) for subset in combinations(vendors, size))

    best_subset: tuple[str, ...] | None = None
    best_choices: dict[int, Candidate | None] = {}
    best_key: tuple[Decimal, int, tuple[str, ...]] | None = None

    for subset in subsets:
        subset_set = set(subset)
        choices: dict[int, Candidate | None] = {}
        total = Decimal(0)
        covered = 0
        for index in range(len(bom)):
            found = next(
                (
                    candidate
                    for candidate in candidates[index]
                    if candidate.offer.vendor in subset_set
                ),
                None,
            )
            choices[index] = found
            if found is not None:
                covered += 1
                total += found.effective_cost
        if covered != len(bom):
            continue
        key = (total, len(subset), subset)
        if best_key is None or key < best_key:
            best_key = key
            best_subset = subset
            best_choices = choices

    if best_subset is not None:
        return best_choices, best_subset

    fallback_key: tuple[int, Decimal, int, tuple[str, ...]] | None = None
    fallback_subset: tuple[str, ...] = ()
    fallback_choices: dict[int, Candidate | None] = {}
    for subset in subsets:
        subset_set = set(subset)
        choices = {}
        total = Decimal(0)
        covered = 0
        for index in range(len(bom)):
            found = next(
                (
                    candidate
                    for candidate in candidates[index]
                    if candidate.offer.vendor in subset_set
                ),
                None,
            )
            choices[index] = found
            if found is not None:
                covered += 1
                total += found.effective_cost
        fallback_candidate_key = (-covered, total, len(subset), subset)
        if fallback_key is None or fallback_candidate_key < fallback_key:
            fallback_key = fallback_candidate_key
            fallback_subset = subset
            fallback_choices = choices
    return fallback_choices, fallback_subset


def select_offers(
    sourcing: Sourcing,
    constraints: SelectionConstraints | Mapping[str, Any] | None = None,
) -> SelectionResult:
    """Choose offers and rank alternates for every BOM line.

    ``constraints`` may be a :class:`SelectionConstraints` or a mapping in its payload shape. A
    mapping with ``None`` is treated as the defaults (14-day lead cap, no vendor cap).
    """
    if constraints is None:
        resolved = SelectionConstraints()
    elif isinstance(constraints, SelectionConstraints):
        resolved = constraints
    elif isinstance(constraints, Mapping):
        resolved = SelectionConstraints.from_mapping(constraints)
    else:
        raise SelectionConstraintsError("constraints must be a SelectionConstraints or object")

    candidates, failures = _candidates_by_line(sourcing, resolved)
    selected_subset: tuple[str, ...] = ()
    if resolved.vendor_count_cap is None:
        choices = _select_without_cap(sourcing.bom, candidates, failures)
    else:
        choices, selected_subset = _select_with_cap(
            sourcing.bom, candidates, failures, resolved.vendor_count_cap
        )

    lines: list[LineSelection] = []
    for index, line in enumerate(sourcing.bom):
        chosen = choices.get(index)
        reasons: tuple[str, ...] = ()
        if chosen is None:
            if candidates[index]:
                subset_text = ", ".join(selected_subset) or "none"
                reasons = (
                    "no feasible offer from the selected vendor set "
                    f"[{subset_text}] under the vendor-count cap "
                    f"{resolved.vendor_count_cap}",
                )
            else:
                reasons = failures[index] or ("no feasible offer",)
        lines.append(
            _line_selection(
                line,
                build_qty=sourcing.build_qty,
                candidates=candidates[index],
                chosen=chosen,
                reasons=reasons,
            )
        )

    chosen_candidates: list[Candidate] = [
        candidate for candidate in choices.values() if candidate is not None
    ]
    total_extended = sum(candidate.extended_cost_minor for candidate in chosen_candidates)
    distinct = sorted({candidate.offer.vendor for candidate in chosen_candidates})
    return SelectionResult(
        lines=tuple(lines),
        total_extended_cost_minor=total_extended,
        distinct_vendors=tuple(distinct),
        constraints=resolved,
    )


def select_offers_from_mapping(
    node: Mapping[str, Any],
    constraints: SelectionConstraints | Mapping[str, Any] | None = None,
) -> SelectionResult:
    """Validate a raw ``/sourcing`` mapping and run :func:`select_offers`."""
    sourcing = Sourcing.model_validate(node)
    return select_offers(sourcing, constraints)
