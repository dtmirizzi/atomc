"""Fabrication-quote orchestration across adapters."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from atomc_core_ir import Assembly, FabQuote, PcbSpec

from ..models import utcnow
from .base import FabAdapter, FabQuoteResult
from .jlcpcb import JlcpcbAdapter

__all__ = ["DEFAULT_FABS", "FabReport", "FabService", "build_fab_adapters"]

DEFAULT_FABS: tuple[str, ...] = ("jlcpcb",)


def build_fab_adapters(
    *,
    env: Mapping[str, str] | None = None,
    transport: httpx.BaseTransport | None = None,
    clock: Callable[[], datetime] | None = None,
    timeout_s: float = 15.0,
) -> dict[str, FabAdapter]:
    """Construct one fabrication adapter per supported fab."""
    kwargs = {
        "env": env,
        "transport": transport,
        "clock": clock,
        "timeout_s": timeout_s,
    }
    return {"jlcpcb": JlcpcbAdapter(**kwargs)}


@dataclass(frozen=True, slots=True)
class FabReport:
    """Aggregated result of quoting one PCB spec across one or more fabs."""

    pcb: PcbSpec
    assembly: Assembly | None
    results: tuple[FabQuoteResult, ...]

    @property
    def quotes(self) -> tuple[FabQuote, ...]:
        return tuple(
            result.quote for result in self.results if result.status == "OK" and result.quote
        )

    @property
    def status(self) -> str:
        statuses = {result.status for result in self.results}
        if "OK" in statuses:
            return "OK"
        if statuses and statuses == {"UNAVAILABLE"}:
            return "UNAVAILABLE"
        return "ERROR"

    @property
    def summary(self) -> str:
        quotes = self.quotes
        if quotes:
            totals = ", ".join(f"{q.fab}={q.total_minor}" for q in quotes)
            return f"{len(quotes)} quote(s) fetched ({totals} minor units)"
        if self.status == "UNAVAILABLE":
            return "no fab returned live data (missing credentials or unreachable endpoint)"
        return "one or more fab responses could not be trusted"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "pcb": self.pcb.model_dump(mode="json"),
            "assembly": self.assembly.model_dump(mode="json") if self.assembly else None,
            "fabs": [result.to_dict() for result in self.results],
            "quotes": [quote.model_dump(mode="json") for quote in self.quotes],
        }


class FabService:
    """Quote a PCB spec across the configured fabrication adapters."""

    def __init__(
        self,
        adapters: Mapping[str, FabAdapter],
        *,
        default_fabs: Iterable[str] = DEFAULT_FABS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.adapters = dict(adapters)
        self.default_fabs = tuple(default_fabs)
        self._clock = clock or utcnow

    def quote(
        self,
        pcb: PcbSpec,
        assembly: Assembly | None = None,
        *,
        fabs: Iterable[str] | None = None,
        force: bool = False,
    ) -> FabReport:
        del force  # no cache; kept in the signature for tool-schema stability
        selected = tuple(fabs) if fabs is not None else self.default_fabs
        if not selected:
            selected = self.default_fabs
        results: list[FabQuoteResult] = []
        for fab in selected:
            adapter = self.adapters.get(fab)
            if adapter is None:
                results.append(
                    FabQuoteResult(
                        fab=fab,
                        status="ERROR",
                        message=f"unknown fab adapter {fab!r}",
                        fetched_at=self._clock(),
                    )
                )
                continue
            results.append(adapter.quote(pcb, assembly))
        return FabReport(pcb=pcb, assembly=assembly, results=tuple(results))
