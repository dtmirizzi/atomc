"""TTL cache behavior with an injected fake clock."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from atomc_plugin_sourcing.cache import OfferCache
from atomc_plugin_sourcing.models import ComponentQuery, OfferPrice, VendorOffer

START = datetime(2026, 11, 5, 12, 0, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: int) -> None:
        self.now += timedelta(**kwargs)


def make_offer() -> VendorOffer:
    return VendorOffer(
        vendor="lcsc",
        sku="C60442",
        stock=320,
        moq=1,
        price_breaks=(OfferPrice(qty=1, unit_price_minor=42),),
        currency="USD",
        fetched_at=START - timedelta(hours=2),
        lead_time_days=7,
    )


def test_cache_hit_until_ttl_then_expires() -> None:
    clock = FakeClock()
    cache = OfferCache(ttl_s=60, clock=clock)
    query = ComponentQuery(lcsc="C60442")

    assert cache.get("lcsc", query) is None
    cache.put("lcsc", query, (make_offer(),), fetched_at=START - timedelta(hours=2))
    entry = cache.get("lcsc", query)
    assert entry is not None
    assert entry.fetched_at == START - timedelta(hours=2)

    clock.advance(seconds=59)
    assert cache.get("lcsc", query) is not None
    clock.advance(seconds=2)
    assert cache.get("lcsc", query) is None


def test_ttl_override_can_disable_cache() -> None:
    clock = FakeClock()
    cache = OfferCache(ttl_s=3600, clock=clock)
    query = ComponentQuery(mpn="STM32F411CEU6")
    cache.put("mouser", query, (make_offer(),), fetched_at=START)
    assert cache.get("mouser", query, ttl_s=0) is None


def test_cache_key_separates_vendor_and_query_fields() -> None:
    cache = OfferCache(clock=FakeClock())
    a = ComponentQuery(mpn="A")
    b = ComponentQuery(mpn="A", qty=2)
    cache.put("mouser", a, (make_offer(),), fetched_at=START)
    assert cache.get("mouser", a) is not None
    assert cache.get("digikey", a) is None
    assert cache.get("mouser", b) is None


def test_eviction_keeps_cache_bounded() -> None:
    clock = FakeClock()
    cache = OfferCache(ttl_s=3600, clock=clock, max_entries=2)
    for index in range(3):
        clock.advance(seconds=1)
        cache.put(
            "lcsc",
            ComponentQuery(lcsc=f"C{index}"),
            (make_offer(),),
            fetched_at=clock.now,
        )
    assert len(cache) == 2
