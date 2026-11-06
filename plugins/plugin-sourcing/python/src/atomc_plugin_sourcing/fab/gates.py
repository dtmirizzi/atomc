"""Pure machine-checkable gate for fabrication quotes.

``fab.quote_under_budget`` compares the cheapest fetched quote for the current PCB spec against
the fabrication budget. It is a deterministic function of the IR document and the cached quotes:
no vendor call, no clock and no file system.

Budget source: the frozen ``fabrication`` node has no budget field, so the gate uses the project
budget at ``/sourcing/budget.total_minor`` when present and otherwise a documented default
threshold (see :data:`atomc_plugin_sourcing.fab.spec.DEFAULT_FAB_BUDGET_MINOR`). The chosen source
is always reported as evidence.

Outcomes:
* ``SKIP`` — no quotes have been fetched yet (nothing to compare).
* ``PASS`` — the cheapest quote is at or under budget.
* ``FAIL`` — every fetched quote is over budget; the cheapest breakdown is reported.
* ``ERROR`` — the stored quotes could not be validated.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from atomc_core_ir import FabQuote
from pydantic import ValidationError

from .spec import budget_for_ir

__all__ = [
    "check_quote_under_budget",
    "evaluate_quote_budget",
    "gate_skip_no_quotes",
]

Status = Literal["PASS", "FAIL", "SKIP", "ERROR"]

NO_QUOTES_MESSAGE = "no quotes fetched yet"


def _text(message: str) -> dict[str, Any]:
    return {"kind": "text", "message": message}


def _json(data: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "json", "data": data}


def _result(
    status: Status,
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


def gate_skip_no_quotes() -> dict[str, Any]:
    """Return the documented SKIP result when no quotes exist."""
    return _result(
        "SKIP",
        NO_QUOTES_MESSAGE,
        evidence=[
            _text("no fab quotes are stored at /fabrication/quotes; run quote_pcb first"),
        ],
    )


def evaluate_quote_budget(
    quotes: Sequence[FabQuote],
    budget_minor: int,
    *,
    budget_source: str,
) -> dict[str, Any]:
    """Pure budget check over already-validated quotes."""
    if not quotes:
        return gate_skip_no_quotes()
    cheapest = min(quotes, key=lambda quote: (quote.total_minor, quote.fab, quote.id))
    breakdown = _json(
        {
            "budget_minor": budget_minor,
            "budget_source": budget_source,
            "cheapest": {
                "id": cheapest.id,
                "fab": cheapest.fab,
                "total_minor": cheapest.total_minor,
                "currency": cheapest.currency,
                "lead_time_days": cheapest.lead_time_days,
                "breakdown": dict(cheapest.breakdown),
            },
            "quotes": [
                {"id": quote.id, "fab": quote.fab, "total_minor": quote.total_minor}
                for quote in quotes
            ],
        }
    )
    if cheapest.total_minor <= budget_minor:
        return _result(
            "PASS",
            (
                f"cheapest fab quote {cheapest.total_minor} {cheapest.currency} minor units "
                f"({cheapest.fab}) is within the {budget_minor} budget"
            ),
            evidence=[
                _text(f"budget source: {budget_source}"),
                breakdown,
            ],
            refs=[cheapest.id],
        )
    return _result(
        "FAIL",
        (
            f"cheapest fab quote {cheapest.total_minor} {cheapest.currency} minor units "
            f"({cheapest.fab}) exceeds the {budget_minor} budget"
        ),
        evidence=[
            _text(f"budget source: {budget_source}"),
            breakdown,
        ],
        suggestions=[
            _text(
                "reduce board quantity, area or finish cost, or raise the recorded project budget"
            )
        ],
        refs=[cheapest.id],
    )


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def check_quote_under_budget(ctx: Any) -> dict[str, Any]:
    """Gate handler: cheapest fetched quote must be within the fabrication budget."""
    getter = getattr(ctx, "ir_get", None)
    if not callable(getter):
        return _result("ERROR", "plugin context does not expose IR reads", refs=[])
    document = await _maybe_await(getter("/"))
    if not isinstance(document, Mapping):
        return _result("ERROR", "IR root is not an object", refs=[])
    fabrication = document.get("fabrication")
    raw_quotes = fabrication.get("quotes") if isinstance(fabrication, Mapping) else None
    if not isinstance(raw_quotes, list) or not raw_quotes:
        return gate_skip_no_quotes()

    quotes: list[FabQuote] = []
    for index, raw in enumerate(raw_quotes):
        try:
            quotes.append(FabQuote.model_validate(raw))
        except ValidationError as exc:
            return _result(
                "ERROR",
                f"/fabrication/quotes[{index}] is not a valid FabQuote",
                evidence=[_text(f"{exc.error_count()} validation error(s)")],
            )

    budget_minor, budget_source = budget_for_ir(document)
    return evaluate_quote_budget(quotes, budget_minor, budget_source=budget_source)
