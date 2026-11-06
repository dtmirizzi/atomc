"""DigiKey adapter.

Targets DigiKey's documented ProductSearch v4 keyword endpoint. DigiKey uses OAuth2; this
adapter consumes an already-issued ``DIGIKEY_ACCESS_TOKEN`` (and optional
``DIGIKEY_CLIENT_ID``), so no token dance is attempted here. Missing credentials make the
query ``UNAVAILABLE`` without a request. Cassettes are synthetic response-shape fixtures only.
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

__all__ = ["DigiKeyAdapter"]


class DigiKeyAdapter(VendorAdapter):
    vendor = "digikey"
    display_name = "DigiKey"
    default_endpoint = "https://api.digikey.com"
    env_keys = ("DIGIKEY_ACCESS_TOKEN",)

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        override = self._env_value("DIGIKEY_API_BASE")
        if override:
            self._endpoint = override.rstrip("/")

    def query_component(self, query: ComponentQuery) -> list[VendorOffer]:
        credentials = self._require_env("DIGIKEY_ACCESS_TOKEN")
        if not query.mpn:
            raise VendorUnavailableError(
                "DigiKey search requires an MPN; this query supplied only an LCSC part number",
                evidence=[{"kind": "text", "message": "no DigiKey request was made"}],
            )

        headers = {
            "Authorization": f"Bearer {credentials['DIGIKEY_ACCESS_TOKEN']}",
            "X-DIGIKEY-Locale-Site": "US",
            "X-DIGIKEY-Locale-Currency": "USD",
            "X-DIGIKEY-Locale-Language": "en",
            "Accept": "application/json",
        }
        client_id = self._env_value("DIGIKEY_CLIENT_ID")
        if client_id:
            headers["X-DIGIKEY-Client-Id"] = client_id

        payload = self._request_json(
            "POST",
            "/products/v4/search/keyword",
            json={"Keywords": query.mpn, "RecordCount": 10, "RecordStart": 0},
            headers=headers,
        )
        document = as_mapping(payload, "response")
        if "Products" not in document:
            raise VendorResponseError(
                "DigiKey response has no Products array",
                evidence=[{"kind": "text", "message": "documented response shape not matched"}],
            )
        products = as_list(document["Products"], "response.Products")

        fetched_at = self._now()
        return [
            self._parse_product(
                as_mapping(raw_product, f"response.Products[{index}]"),
                fetched_at=fetched_at,
                context=f"response.Products[{index}]",
            )
            for index, raw_product in enumerate(products)
        ]

    def _parse_product(
        self,
        product: dict[str, Any],
        *,
        fetched_at: Any,
        context: str,
    ) -> VendorOffer:
        sku = str(required(product, "DigiKeyPartNumber", context))
        stock = parse_int(
            required(product, "QuantityAvailable", context),
            f"{context}.QuantityAvailable",
            minimum=0,
        )
        raw_mpn = product.get("ManufacturerPartNumber")
        if raw_mpn is not None and not isinstance(raw_mpn, str):
            raise VendorResponseError(
                f"malformed vendor response: {context}.ManufacturerPartNumber"
            )
        raw_url = product.get("ProductUrl")
        if raw_url is not None and not isinstance(raw_url, str):
            raise VendorResponseError(f"malformed vendor response: {context}.ProductUrl")

        currency = str(product.get("Currency") or "USD").upper()
        raw_breaks = product.get("StandardPricing")
        breaks: list[OfferPrice] = []
        if raw_breaks is not None:
            for index, raw_break in enumerate(as_list(raw_breaks, f"{context}.StandardPricing")):
                item_context = f"{context}.StandardPricing[{index}]"
                item = as_mapping(raw_break, item_context)
                qty = parse_int(
                    required(item, "BreakQuantity", item_context),
                    f"{item_context}.BreakQuantity",
                    minimum=1,
                )
                price = parse_money_minor(
                    required(item, "UnitPrice", item_context),
                    f"{item_context}.UnitPrice",
                )
                breaks.append(OfferPrice(qty=qty, unit_price_minor=price))
                if isinstance(item.get("Currency"), str):
                    currency = item["Currency"].upper()
        elif product.get("UnitPrice") is not None:
            breaks.append(
                OfferPrice(
                    qty=1,
                    unit_price_minor=parse_money_minor(
                        product["UnitPrice"], f"{context}.UnitPrice"
                    ),
                )
            )

        return VendorOffer(
            vendor=self.vendor,
            sku=sku,
            stock=stock,
            moq=parse_int(
                product.get("MinimumQuantity", 1),
                f"{context}.MinimumQuantity",
                minimum=1,
            ),
            price_breaks=tuple(breaks),
            currency=currency,
            fetched_at=fetched_at,
            lead_time_days=self._lead_days(product.get("ManufacturerLeadWeeks"), context),
            url=raw_url,
            mpn=raw_mpn,
        )

    @staticmethod
    def _lead_days(value: Any, context: str) -> int | None:
        if value is None or value == "":
            return None
        if isinstance(value, int) and not isinstance(value, bool):
            return parse_int(value, f"{context}.ManufacturerLeadWeeks", minimum=0) * 7
        if isinstance(value, str):
            if value.strip().isdigit():
                return int(value.strip()) * 7
            return parse_lead_time_days(value, f"{context}.ManufacturerLeadWeeks")
        raise VendorResponseError(f"malformed vendor response: {context}.ManufacturerLeadWeeks")
