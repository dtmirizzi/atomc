"""Vendor query orchestration with TTL caching and honest aggregate outcomes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .adapters import DEFAULT_VENDORS
from .adapters.base import VendorAdapter
from .cache import OfferCache
from .models import AdapterResult, ComponentQuery, VendorOffer, format_timestamp, utcnow

__all__ = ["QueryReport", "SourcingService"]


@dataclass(frozen=True, slots=True)
class QueryReport:
    """Aggregated result of querying one or more vendors."""

    query: ComponentQuery
    results: tuple[AdapterResult, ...]

    @property
    def offers(self) -> tuple[VendorOffer, ...]:
        return tuple(offer for result in self.results for offer in result.offers)

    @property
    def available(self) -> bool:
        return any(result.status == "OK" and result.offers for result in self.results)

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
        offer_count = len(self.offers)
        ok_vendors = [result.vendor for result in self.results if result.status == "OK"]
        if self.status == "OK" and offer_count:
            return (
                f"{offer_count} offer(s) from {len(ok_vendors)} vendor(s): {', '.join(ok_vendors)}"
            )
        if self.status == "OK":
            return "vendor responses contained no matching offers"
        if self.status == "UNAVAILABLE":
            return "no vendor returned live data (missing credentials or unreachable endpoint)"
        return "one or more vendor responses could not be trusted"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "available": self.available,
            "summary": self.summary,
            "query": self.query.to_dict(),
            "queried_at": format_timestamp(
                max((r.fetched_at for r in self.results), default=utcnow())
            ),
            "vendors": [result.to_dict() for result in self.results],
            "offers": [offer.to_dict() for offer in self.offers],
        }


class SourcingService:
    """Query adapters, cache successful responses, and aggregate outcomes."""

    def __init__(
        self,
        adapters: Mapping[str, VendorAdapter],
        *,
        cache: OfferCache | None = None,
        default_vendors: Iterable[str] = DEFAULT_VENDORS,
        clock: Any = None,
    ) -> None:
        self.adapters = dict(adapters)
        self.default_vendors = tuple(default_vendors)
        self.cache = cache if cache is not None else OfferCache(clock=clock)

    def query(
        self,
        query: ComponentQuery,
        *,
        vendors: Iterable[str] | None = None,
        force: bool = False,
        ttl_s: int | None = None,
    ) -> QueryReport:
        selected = tuple(vendors) if vendors is not None else self.default_vendors
        if not selected:
            selected = self.default_vendors
        results: list[AdapterResult] = []
        for vendor in selected:
            adapter = self.adapters.get(vendor)
            if adapter is None:
                results.append(
                    AdapterResult(
                        vendor=vendor,
                        status="ERROR",
                        message=f"unknown vendor adapter {vendor!r}",
                        fetched_at=utcnow(),
                    )
                )
                continue

            entry = None if force else self.cache.get(vendor, query, ttl_s=ttl_s)
            if entry is not None:
                results.append(
                    AdapterResult(
                        vendor=vendor,
                        status="OK",
                        offers=entry.offers,
                        fetched_at=entry.fetched_at,
                        cached=True,
                        evidence=(
                            {
                                "kind": "text",
                                "message": (
                                    "cache hit; fetched_at is the original fetch time, not now"
                                ),
                            },
                        ),
                    )
                )
                continue

            result = adapter.query(query)
            if result.status == "OK":
                self.cache.put(
                    vendor,
                    query,
                    result.offers,
                    fetched_at=result.fetched_at,
                    ttl_s=ttl_s,
                )
            results.append(result)
        return QueryReport(query=query, results=tuple(results))


def age_seconds(fetched_at: datetime, now: datetime | None = None) -> int:
    """Return the age of a fetched timestamp in whole seconds (helper for reports)."""
    current = now or utcnow()
    return max(0, int((current - fetched_at).total_seconds()))
