"""LCSC adapter.

LCSC has no supported public API. This adapter targets the public product JSON served by the
LCSC web frontend (``wmsc.lcsc.com``); the endpoint is configurable via ``LCSC_API_BASE`` so a
deployment can point at a permitted mirror (for example a self-hosted ``jlcparts`` export).
Requests need no API key. The committed cassettes are synthetic and model this documented
shape only; no live vendor call was made while developing or testing this package.
"""

from __future__ import annotations

from typing import Any

from ..errors import VendorResponseError
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

__all__ = ["LcscAdapter"]


class LcscAdapter(VendorAdapter):
    vendor = "lcsc"
    display_name = "LCSC"
    default_endpoint = "https://wmsc.lcsc.com/wmsc"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        override = self._env_value("LCSC_API_BASE")
        if override:
            self._endpoint = override.rstrip("/")

    def query_component(self, query: ComponentQuery) -> list[VendorOffer]:
        if query.lcsc:
            payload = self._request_json(
                "GET",
                "/product/query/productDetail",
                params={"productCode": query.lcsc},
            )
            document = as_mapping(payload, "response")
            self._check_code(document)
            raw = document.get("result")
            products: list[Any] = [] if raw is None else [raw]
            context = "response.result"
        else:
            payload = self._request_json(
                "GET",
                "/product/query/productList",
                params={"keyword": query.mpn},
            )
            document = as_mapping(payload, "response")
            self._check_code(document)
            result = as_mapping(document.get("result") or {}, "response.result")
            products = as_list(result.get("productList") or [], "response.result.productList")
            context = "response.result.productList"

        offers: list[VendorOffer] = []
        fetched_at = self._now()
        for index, raw_product in enumerate(products):
            offers.append(
                self._parse_product(
                    as_mapping(raw_product, f"{context}[{index}]"),
                    fetched_at=fetched_at,
                    context=f"{context}[{index}]",
                )
            )
        return offers

    @staticmethod
    def _check_code(document: dict[str, Any]) -> None:
        if "code" not in document:
            return
        code = document["code"]
        if code not in (0, 200, "0", "200"):
            raise VendorResponseError(
                f"LCSC returned code {code!r}: {document.get('message') or 'no message'}",
                evidence=[{"kind": "text", "message": "vendor response indicated an error"}],
            )

    def _parse_product(
        self,
        product: dict[str, Any],
        *,
        fetched_at: Any,
        context: str,
    ) -> VendorOffer:
        sku = str(required(product, "productCode", context))
        stock = parse_int(
            required(product, "stockNumber", context),
            f"{context}.stockNumber",
            minimum=0,
        )
        raw_breaks = as_list(product.get("priceBreaks") or [], f"{context}.priceBreaks")
        breaks: list[OfferPrice] = []
        for index, raw_break in enumerate(raw_breaks):
            item = as_mapping(raw_break, f"{context}.priceBreaks[{index}]")
            qty = parse_int(
                required(item, "quantity", f"{context}.priceBreaks[{index}]"),
                f"{context}.priceBreaks[{index}].quantity",
                minimum=1,
            )
            price = parse_money_minor(
                required(item, "price", f"{context}.priceBreaks[{index}]"),
                f"{context}.priceBreaks[{index}].price",
            )
            breaks.append(OfferPrice(qty=qty, unit_price_minor=price))

        raw_mpn = product.get("productModel")
        if raw_mpn is not None and not isinstance(raw_mpn, str):
            raise VendorResponseError(f"malformed vendor response: {context}.productModel")
        raw_url = product.get("productUrl")
        if raw_url is not None and not isinstance(raw_url, str):
            raise VendorResponseError(f"malformed vendor response: {context}.productUrl")

        return VendorOffer(
            vendor=self.vendor,
            sku=sku,
            stock=stock,
            moq=parse_int(product.get("moq", 1), f"{context}.moq", minimum=1),
            price_breaks=tuple(breaks),
            currency=str(product.get("currency") or "USD").upper(),
            fetched_at=fetched_at,
            lead_time_days=parse_lead_time_days(
                product.get("leadTimeDays"), f"{context}.leadTimeDays"
            ),
            url=raw_url,
            mpn=raw_mpn,
        )
