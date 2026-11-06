"""Service orchestration: caching, aggregate honesty and vendor selection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from atomc_plugin_sourcing.adapters.base import VendorAdapter
from atomc_plugin_sourcing.cache import OfferCache
from atomc_plugin_sourcing.errors import VendorResponseError, VendorUnavailableError
from atomc_plugin_sourcing.models import ComponentQuery, OfferPrice, VendorOffer
from atomc_plugin_sourcing.service import SourcingService

START = datetime(2026, 11, 5, 12, 0, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: int) -> None:
        self.now += timedelta(**kwargs)


class FakeAdapter(VendorAdapter):
    vendor = "fake"
    display_name = "Fake"
    default_endpoint = "https://fake.invalid"

    def __init__(self, *, failure: str | None = None, clock: Any = None) -> None:
        super().__init__(env={}, clock=clock)
        self.calls = 0
        self.failure = failure

    def query_component(self, query: ComponentQuery) -> list[VendorOffer]:
        self.calls += 1
        if self.failure == "unavailable":
            raise VendorUnavailableError("no credentials")
        if self.failure == "malformed":
            raise VendorResponseError("bad shape")
        return [
            VendorOffer(
                vendor=self.vendor,
                sku=f"SKU-{query.mpn or query.lcsc}",
                stock=10,
                moq=1,
                price_breaks=(OfferPrice(qty=1, unit_price_minor=100),),
                currency="USD",
                fetched_at=self._now(),
            )
        ]


def make_service(adapter: FakeAdapter, clock: FakeClock) -> SourcingService:
    return SourcingService(
        {"fake": adapter},
        cache=OfferCache(ttl_s=7200, clock=clock),
        default_vendors=("fake",),
        clock=clock,
    )


def test_cache_hit_is_labelled_and_preserves_original_fetched_at() -> None:
    clock = FakeClock()
    adapter = FakeAdapter(clock=clock)
    service = make_service(adapter, clock)
    query = ComponentQuery(mpn="STM32F411CEU6")

    first = service.query(query)
    assert first.status == "OK"
    assert first.results[0].cached is False
    assert first.results[0].fetched_at == START
    assert adapter.calls == 1

    clock.advance(hours=1)
    second = service.query(query)
    assert second.results[0].cached is True
    assert second.results[0].fetched_at == START
    assert adapter.calls == 1

    clock.advance(hours=2)
    third = service.query(query)
    assert third.results[0].cached is False
    assert third.results[0].fetched_at == clock.now
    assert adapter.calls == 2


def test_force_bypasses_cache() -> None:
    clock = FakeClock()
    adapter = FakeAdapter(clock=clock)
    service = make_service(adapter, clock)
    query = ComponentQuery(mpn="STM32F411CEU6")
    service.query(query)
    service.query(query, force=True)
    assert adapter.calls == 2


def test_unavailable_and_error_are_never_cached() -> None:
    clock = FakeClock()
    unavailable = FakeAdapter(failure="unavailable", clock=clock)
    service = make_service(unavailable, clock)
    query = ComponentQuery(mpn="X")
    assert service.query(query).status == "UNAVAILABLE"
    assert service.query(query).status == "UNAVAILABLE"
    assert unavailable.calls == 2

    malformed = FakeAdapter(failure="malformed", clock=clock)
    service = make_service(malformed, clock)
    assert service.query(query).status == "ERROR"
    assert malformed.calls == 1


def test_unknown_vendor_is_an_explicit_error() -> None:
    clock = FakeClock()
    service = make_service(FakeAdapter(clock=clock), clock)
    report = service.query(ComponentQuery(mpn="X"), vendors=["nope"])
    assert report.status == "ERROR"
    assert report.results[0].vendor == "nope"
    assert report.offers == ()
    assert "unknown vendor adapter" in (report.results[0].message or "")


def test_mixed_outcomes_keep_ok_offers_and_expose_failures() -> None:
    clock = FakeClock()
    good = FakeAdapter(clock=clock)
    bad = FakeAdapter(failure="unavailable", clock=clock)
    service = SourcingService(
        {"good": good, "bad": bad}, default_vendors=("good", "bad"), clock=clock
    )
    report = service.query(ComponentQuery(mpn="X"), vendors=["good", "bad"])
    assert report.status == "OK"
    assert report.available is True
    assert len(report.offers) == 1
    assert {result.status for result in report.results} == {"OK", "UNAVAILABLE"}
