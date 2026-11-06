"""Nexar adapter.

Targets Nexar's documented GraphQL ``supSearchMpn`` response. Nexar is an aggregator, so an
offer's seller is preserved in the returned SKU/URL but the frozen IR ``Offer.vendor`` enum has
no ``nexar`` member; normalization therefore records ``vendor: "other"``. The adapter identity
remains ``nexar`` in the query report. Requires ``NEXAR_ACCESS_TOKEN`` (or ``NEXAR_TOKEN``);
missing credentials make the query ``UNAVAILABLE`` without a request.
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
    required,
)
from .base import VendorAdapter

__all__ = ["NexarAdapter"]

_SEARCH_QUERY = """
query SearchMpn($mpn: String!) {
  supSearchMpn(mpn: $mpn, limit: 10) {
    results {
      part {
        mpn
        sellers {
          company { name }
          offers {
            sku
            inventoryLevel
            moq
            factoryLeadTime
            clickUrl
            prices { quantity price currency }
          }
        }
      }
    }
  }
}
"""


class NexarAdapter(VendorAdapter):
    vendor = "nexar"
    display_name = "Nexar"
    default_endpoint = "https://api.nexar.com"
    env_keys = ("NEXAR_ACCESS_TOKEN", "NEXAR_TOKEN")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        override = self._env_value("NEXAR_API_BASE")
        if override:
            self._endpoint = override.rstrip("/")

    def query_component(self, query: ComponentQuery) -> list[VendorOffer]:
        token = self._env_value("NEXAR_ACCESS_TOKEN") or self._env_value("NEXAR_TOKEN")
        if token is None:
            raise VendorUnavailableError(
                "Nexar requires credentials in NEXAR_ACCESS_TOKEN (or NEXAR_TOKEN); "
                "no live call was made",
                evidence=[
                    {
                        "kind": "text",
                        "message": (
                            "missing required environment variable(s): "
                            "NEXAR_ACCESS_TOKEN, NEXAR_TOKEN"
                        ),
                    }
                ],
            )
        if not query.mpn:
            raise VendorUnavailableError(
                "Nexar search requires an MPN; this query supplied only an LCSC part number",
                evidence=[{"kind": "text", "message": "no Nexar request was made"}],
            )

        payload = self._request_json(
            "POST",
            "/graphql",
            json={"query": _SEARCH_QUERY, "variables": {"mpn": query.mpn}},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        document = as_mapping(payload, "response")
        errors = as_list(document.get("Errors") or document.get("errors") or [], "response.errors")
        if errors:
            messages = "; ".join(str(item) for item in errors)
            raise VendorResponseError(
                f"Nexar GraphQL returned errors: {messages}",
                evidence=[{"kind": "text", "message": messages}],
            )
        data = as_mapping(required(document, "data", "response"), "response.data")
        search = as_mapping(
            required(data, "supSearchMpn", "response.data"), "response.data.supSearchMpn"
        )
        results = as_list(search.get("results") or [], "response.data.supSearchMpn.results")

        fetched_at = self._now()
        offers: list[VendorOffer] = []
        for result_index, raw_result in enumerate(results):
            result_context = f"response.data.supSearchMpn.results[{result_index}]"
            result = as_mapping(raw_result, result_context)
            part = as_mapping(required(result, "part", result_context), f"{result_context}.part")
            raw_mpn = part.get("mpn")
            if raw_mpn is not None and not isinstance(raw_mpn, str):
                raise VendorResponseError(f"malformed vendor response: {result_context}.part.mpn")
            sellers = as_list(part.get("sellers") or [], f"{result_context}.part.sellers")
            for seller_index, raw_seller in enumerate(sellers):
                seller_context = f"{result_context}.part.sellers[{seller_index}]"
                seller = as_mapping(raw_seller, seller_context)
                seller_offers = as_list(seller.get("offers") or [], f"{seller_context}.offers")
                for offer_index, raw_offer in enumerate(seller_offers):
                    offer_context = f"{seller_context}.offers[{offer_index}]"
                    offers.append(
                        self._parse_offer(
                            as_mapping(raw_offer, offer_context),
                            fetched_at=fetched_at,
                            mpn=raw_mpn,
                            context=offer_context,
                        )
                    )
        return offers

    def _parse_offer(
        self,
        offer: dict[str, Any],
        *,
        fetched_at: Any,
        mpn: str | None,
        context: str,
    ) -> VendorOffer:
        sku = str(required(offer, "sku", context))
        stock = parse_int(
            required(offer, "inventoryLevel", context),
            f"{context}.inventoryLevel",
            minimum=0,
        )
        raw_url = offer.get("clickUrl")
        if raw_url is not None and not isinstance(raw_url, str):
            raise VendorResponseError(f"malformed vendor response: {context}.clickUrl")

        currency = "USD"
        breaks: list[OfferPrice] = []
        for index, raw_price in enumerate(as_list(offer.get("prices") or [], f"{context}.prices")):
            price_context = f"{context}.prices[{index}]"
            item = as_mapping(raw_price, price_context)
            qty = parse_int(
                required(item, "quantity", price_context),
                f"{price_context}.quantity",
                minimum=1,
            )
            breaks.append(
                OfferPrice(
                    qty=qty,
                    unit_price_minor=parse_money_minor(
                        required(item, "price", price_context),
                        f"{price_context}.price",
                    ),
                )
            )
            if isinstance(item.get("currency"), str):
                currency = item["currency"].upper()

        return VendorOffer(
            vendor=self.vendor,
            sku=sku,
            stock=stock,
            moq=parse_int(offer.get("moq", 1), f"{context}.moq", minimum=1),
            price_breaks=tuple(breaks),
            currency=currency,
            fetched_at=fetched_at,
            lead_time_days=parse_lead_time_days(
                offer.get("factoryLeadTime"), f"{context}.factoryLeadTime"
            ),
            url=raw_url,
            mpn=mpn,
        )
