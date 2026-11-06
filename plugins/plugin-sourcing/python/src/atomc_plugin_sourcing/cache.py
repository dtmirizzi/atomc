"""A small TTL cache for vendor query results.

Cache hits keep the original ``fetched_at`` (they are old data, labelled ``cached: true``) and
never refresh it. The clock is injectable so TTL behaviour is tested deterministically.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from .models import ComponentQuery, VendorOffer, utcnow

__all__ = ["DEFAULT_TTL_S", "CacheEntry", "OfferCache"]

DEFAULT_TTL_S = 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class CacheEntry:
    """A cached successful query result."""

    vendor: str
    offers: tuple[VendorOffer, ...]
    fetched_at: datetime
    stored_at: datetime


class OfferCache:
    """In-memory key/value cache keyed by vendor plus query, with a configurable TTL."""

    def __init__(
        self,
        *,
        ttl_s: int = DEFAULT_TTL_S,
        clock: Callable[[], datetime] | None = None,
        max_entries: int = 512,
    ) -> None:
        if ttl_s < 0:
            raise ValueError("ttl_s must be >= 0")
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self.ttl_s = ttl_s
        self.max_entries = max_entries
        self._clock = clock or utcnow
        self._entries: dict[str, CacheEntry] = {}

    @staticmethod
    def key(vendor: str, query: ComponentQuery) -> str:
        return f"{vendor}|{query.cache_key()}"

    def get(
        self,
        vendor: str,
        query: ComponentQuery,
        *,
        ttl_s: int | None = None,
    ) -> CacheEntry | None:
        """Return a live cache entry, or delete and return ``None`` when expired."""
        key = self.key(vendor, query)
        entry = self._entries.get(key)
        if entry is None:
            return None
        ttl = self.ttl_s if ttl_s is None else ttl_s
        if ttl <= 0 or self._clock() - entry.stored_at >= timedelta(seconds=ttl):
            self._entries.pop(key, None)
            return None
        return entry

    def put(
        self,
        vendor: str,
        query: ComponentQuery,
        offers: tuple[VendorOffer, ...],
        *,
        fetched_at: datetime,
        ttl_s: int | None = None,
    ) -> CacheEntry:
        """Cache a successful query result (including a genuinely empty result)."""
        ttl = self.ttl_s if ttl_s is None else ttl_s
        now = self._clock()
        entry = CacheEntry(
            vendor=vendor,
            offers=offers,
            fetched_at=fetched_at,
            stored_at=now,
        )
        if ttl >= 0:
            self._entries[self.key(vendor, query)] = entry
            self._evict_if_needed()
        return entry

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)

    def _evict_if_needed(self) -> None:
        while len(self._entries) > self.max_entries:
            oldest = min(self._entries.items(), key=lambda item: item[1].stored_at)[0]
            self._entries.pop(oldest, None)
