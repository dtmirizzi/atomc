"""Mouser adapter.

Targets the documented Mouser Search API v1 ``/api/v1/search/partnumber`` response. The adapter
requires ``MOUSER_API_KEY``; without it the query is ``UNAVAILABLE`` and no request is made.
The committed cassettes are synthetic, model the documented response shape and were never
captured from a live call.
"""

from __future__ import annotations

from typing import Any

from ..errors import VendorResponseError, VendorUnavailableError
from ..models import ComponentQuery, OfferPrice, VendorOffer
from ..parsing import (
    as_list,
    as_mapping,
    parse_int,
    parse_lead_time_days,
    parse_money_minor,
    parse_stock_text,
    required,
)
from .base import VendorAdapter

__all__ = ["MouserAdapter"]


class MouserAdapter(VendorAdapter):
    vendor = "mouser"
    display_name = "Mouser"
    default_endpoint = "https://api.mouser.com"
    env_keys = ("MOUSER_API_KEY",)

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        override = self._env_value("MOUSER_API_BASE")
        if override:
            self._endpoint = override.rstrip("/")

    def query_component(self, query: ComponentQuery) -> list[VendorOffer]:
        credentials = self._require_env("MOUSER_API_KEY")
        if not query.mpn:
            raise VendorUnavailableError(
                "Mouser search requires an MPN; this query supplied only an LCSC part number",
                evidence=[{"kind": "text", "message": "no Mouser request was made"}],
            )

        payload = self._request_json(
            "POST",
            "/api/v1/search/partnumber",
            params={"apiKey": credentials["MOUSER_API_KEY"]},
            json={
                "SearchByPartRequest": {
                    "mouserPartNumber": query.mpn,
                    "partSearchOptions": "Exact",
                }
            },
        )
        document = as_mapping(payload, "response")
        errors = as_list(document.get("Errors") or [], "response.Errors")
        if errors:
            messages = "; ".join(str(item) for item in errors)
            raise VendorResponseError(
                f"Mouser API returned errors: {messages}",
                evidence=[{"kind": "text", "message": messages}],
            )
        search = as_mapping(
            required(document, "SearchResults", "response"), "response.SearchResults"
        )
        parts = as_list(search.get("Parts") or [], "response.SearchResults.Parts")

        fetched_at = self._now()
        return [
            self._parse_part(
                as_mapping(raw_part, f"response.SearchResults.Parts[{index}]"),
                fetched_at=fetched_at,
                context=f"response.SearchResults.Parts[{index}]",
            )
            for index, raw_part in enumerate(parts)
        ]

    def _parse_part(
        self,
        part: dict[str, Any],
        *,
        fetched_at: Any,
        context: str,
    ) -> VendorOffer:
        sku = str(required(part, "MouserPartNumber", context))
        stock = parse_stock_text(required(part, "Availability", context), f"{context}.Availability")
        raw_mpn = part.get("ManufacturerPartNumber")
        if raw_mpn is not None and not isinstance(raw_mpn, str):
            raise VendorResponseError(
                f"malformed vendor response: {context}.ManufacturerPartNumber"
            )
        raw_url = part.get("ProductDetailUrl")
        if raw_url is not None and not isinstance(raw_url, str):
            raise VendorResponseError(f"malformed vendor response: {context}.ProductDetailUrl")

        raw_breaks = as_list(part.get("PriceBreaks") or [], f"{context}.PriceBreaks")
        breaks: list[OfferPrice] = []
        currency = str(part.get("Currency") or "USD").upper()
        for index, raw_break in enumerate(raw_breaks):
            item_context = f"{context}.PriceBreaks[{index}]"
            item = as_mapping(raw_break, item_context)
            prices = item.get("Price")
            if not isinstance(prices, list):
                # Some documented responses use a single Price string.
                prices = [prices] if prices is not None else []
            if not prices:
                raise VendorResponseError(f"malformed vendor response: {item_context}.Price")
            qty = parse_int(
                required(item, "Quantity", item_context),
                f"{item_context}.Quantity",
                minimum=1,
            )
            breaks.append(
                OfferPrice(
                    qty=qty,
                    unit_price_minor=parse_money_minor(prices[0], f"{item_context}.Price"),
                )
            )
            if isinstance(item.get("Currency"), str):
                currency = item["Currency"].upper()

        moq = parse_int(part.get("MOQ", 1), f"{context}.MOQ", minimum=1)
        return VendorOffer(
            vendor=self.vendor,
            sku=sku,
            stock=stock,
            moq=moq,
            price_breaks=tuple(breaks),
            currency=currency,
            fetched_at=fetched_at,
            lead_time_days=parse_lead_time_days(part.get("LeadTime"), f"{context}.LeadTime"),
            url=raw_url,
            mpn=raw_mpn,
        )
