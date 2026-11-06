"""The ``plugin:sourcing`` implementation: vendor queries and BOM offer refresh.

Handlers follow the daemon's tolerant invocation: ``(ctx, payload)``. Writes only ever go
through the injected context so the daemon enforces this plugin's ``/sourcing`` scope.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import httpx

from .adapters import build_adapters
from .adapters.base import VendorAdapter
from .cache import DEFAULT_TTL_S, OfferCache
from .manifest import manifest_dict
from .optimizer import (
    all_in_stock_gate,
    cost_under_budget_gate,
    lead_time_under_days_gate,
    optimize_payload,
)
from .service import SourcingService
from .tools import query_payload, refresh_payload

__all__ = ["SourcingPlugin", "plugin"]


def _env_ttl(env: Mapping[str, str]) -> int:
    raw = env.get("ATOMC_SOURCING_CACHE_TTL_S")
    if raw is None:
        return DEFAULT_TTL_S
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TTL_S
    return value if value >= 0 else DEFAULT_TTL_S


class SourcingPlugin:
    """Vendor sourcing adapters with TTL caching, exposed as two agent tools."""

    def __init__(
        self,
        *,
        adapters: Mapping[str, VendorAdapter] | None = None,
        service: SourcingService | None = None,
        cache: OfferCache | None = None,
        env: Mapping[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
        clock: Any = None,
        timeout_s: float = 15.0,
    ) -> None:
        # The daemon's entry-point resolver validates ``.manifest`` into its own model.
        self.manifest: dict[str, Any] = manifest_dict()
        resolved_env: Mapping[str, str] = env if env is not None else os.environ
        self._clock = clock
        if service is not None:
            self.service = service
        else:
            adapter_map = (
                adapters
                if adapters is not None
                else build_adapters(
                    env=resolved_env,
                    transport=transport,
                    clock=clock,
                    timeout_s=timeout_s,
                )
            )
            offer_cache = (
                cache
                if cache is not None
                else OfferCache(
                    ttl_s=_env_ttl(resolved_env),
                    clock=clock,
                )
            )
            self.service = SourcingService(adapter_map, cache=offer_cache, clock=clock)

    async def query_tool(
        self,
        ctx: Any,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await query_payload(self.service, ctx, payload)

    async def refresh_tool(
        self,
        ctx: Any,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await refresh_payload(self.service, ctx, payload)

    async def optimize_tool(
        self,
        ctx: Any,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await optimize_payload(ctx, payload)

    async def check_all_in_stock(self, ctx: Any) -> dict[str, Any]:
        return await all_in_stock_gate(ctx)

    async def check_cost_under_budget(self, ctx: Any) -> dict[str, Any]:
        return await cost_under_budget_gate(ctx)

    async def check_lead_time_under_days(self, ctx: Any) -> dict[str, Any]:
        return await lead_time_under_days_gate(ctx)


plugin = SourcingPlugin()

__all__ = ["SourcingPlugin", "plugin"]
