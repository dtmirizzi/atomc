"""JLCPCB fabrication-quote adapter.

JLCPCB exposes a PCB price calculator through its partner/open API. This adapter maps the frozen
:class:`~atomc_core_ir.PcbSpec` (plus an optional assembly request) onto the documented request
body, signs it with the documented ``JOP-HMAC-SHA256`` scheme, and parses the documented response
envelope (``{code, data, message}``) into a frozen :class:`~atomc_core_ir.FabQuote`.

**No live call is ever made while developing or testing this package.** The tests replay a
synthetic cassette that models the documented request/response shape only, and the endpoint,
signing details and field names should be re-checked against the login-gated JLCPCB documentation
before any production use. Missing ``JLCPCB_APP_ID``/``JLCPCB_ACCESS_KEY`` fails closed with an
honest ``UNAVAILABLE`` result.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any

from atomc_core_ir import Assembly, FabQuote, PcbSpec

from ..errors import VendorResponseError
from ..parsing import as_list, as_mapping, parse_lead_time_days, parse_money_minor, required
from .base import FabAdapter

__all__ = ["COLOR_ENUM", "FINISH_ENUM", "SIDE_ENUM", "JlcpcbAdapter", "quote_id_for_spec"]

# Documented calculators use numeric enums for color/finish/side.
COLOR_ENUM: dict[str, int] = {
    "green": 1,
    "red": 2,
    "yellow": 3,
    "blue": 4,
    "white": 5,
    "black": 6,
}
FINISH_ENUM: dict[str, int] = {"HASL": 1, "LF-HASL": 2, "ENIG": 3}
SIDE_ENUM: dict[str, int] = {"top": 1, "bottom": 2, "both": 3}


def quote_id_for_spec(pcb: PcbSpec, assembly: Assembly | None = None) -> str:
    """Return a deterministic ``quote:jlcpcb_*`` id for a spec (stable across refetches)."""
    payload = {
        "layers": pcb.layers,
        "width_mm": pcb.width_mm,
        "height_mm": pcb.height_mm,
        "thickness_mm": pcb.thickness_mm,
        "finish": pcb.finish,
        "color": pcb.color.lower(),
        "qty": pcb.qty,
        "assembly": None
        if assembly is None
        else {"side": assembly.side, "parts_count": assembly.parts_count},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"quote:jlcpcb_{digest}"


class JlcpcbAdapter(FabAdapter):
    """JLCPCB PCB (+ assembly) price calculator."""

    fab = "jlcpcb"
    display_name = "JLCPCB"
    default_endpoint = "https://jlcpcb.com/api/overseas/openapi"
    env_keys = ("JLCPCB_APP_ID", "JLCPCB_ACCESS_KEY")
    quote_path = "/pcb/calculate"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        override = self._env_value("JLCPCB_API_BASE")
        if override:
            self._endpoint = override.rstrip("/")

    # -- request ------------------------------------------------------------

    def request_body(self, pcb: PcbSpec, assembly: Assembly | None = None) -> dict[str, Any]:
        """Map a spec to the documented request body (also used by request-mapping tests)."""
        pcb_param: dict[str, Any] = {
            "layer": pcb.layers,
            "width": pcb.width_mm,
            "length": pcb.height_mm,
            "qty": pcb.qty,
            "thickness": pcb.thickness_mm,
            "pcbColor": COLOR_ENUM.get(pcb.color.strip().lower(), COLOR_ENUM["green"]),
            "surfaceFinish": FINISH_ENUM[pcb.finish],
            "copperWeight": 1.0,
            "goldFinger": 0,
            "materialDetails": "",
            "panelFlag": 0,
            "differentDesign": 1,
        }
        body: dict[str, Any] = {"orderType": 1, "pcbParam": pcb_param, "country": "US"}
        if assembly is not None:
            body["assemblyParam"] = {
                "side": SIDE_ENUM[assembly.side],
                "partsCount": assembly.parts_count,
            }
        return body

    def auth_headers(self, body_text: str) -> dict[str, str]:
        """Build the documented ``JOP-HMAC-SHA256`` authorization header for a body.

        The signature covers ``"<method>\\n<path>\\n<timestamp>\\n<nonce>\\n<body>\\n"``. The
        nonce here is derived deterministically from the body and timestamp (a real deployment
        should use a random nonce); the signing scheme is modelled on the documented API and is
        not exercised against a live endpoint.
        """
        credentials = self._require_env(*self.env_keys)
        app_id = credentials["JLCPCB_APP_ID"]
        access_key = credentials["JLCPCB_ACCESS_KEY"]
        timestamp = str(int(self._now().timestamp()))
        nonce = hashlib.sha256(f"{app_id}:{timestamp}:{body_text}".encode()).hexdigest()[:32]
        signing = f"POST\n{self.quote_path}\n{timestamp}\n{nonce}\n{body_text}\n"
        signature = hmac.new(
            access_key.encode("utf-8"), signing.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        authorization = (
            f'JOP-HMAC-SHA256 appid="{app_id}",accesskey="{access_key}",'
            f'timestamp="{timestamp}",nonce="{nonce}",signature="{signature}"'
        )
        return {"Authorization": authorization, "Content-Type": "application/json"}

    def quote_pcb(self, pcb: PcbSpec, assembly: Assembly | None = None) -> FabQuote:
        self._require_env(*self.env_keys)
        body = self.request_body(pcb, assembly)
        body_text = json.dumps(body, separators=(",", ":"))
        payload = self._request_json(
            "POST",
            self.quote_path,
            content=body_text,
            headers=self.auth_headers(body_text),
        )
        return self._parse_quote(payload, pcb, assembly)

    # -- response -----------------------------------------------------------

    def _parse_quote(
        self,
        payload: Any,
        pcb: PcbSpec,
        assembly: Assembly | None,
    ) -> FabQuote:
        document = as_mapping(payload, "response")
        code = document.get("code")
        if code not in (0, 200, "0", "200"):
            raise VendorResponseError(
                f"JLCPCB returned code {code!r}: {document.get('message') or 'no message'}",
                evidence=[{"kind": "text", "message": "vendor response indicated an error"}],
            )
        data = as_mapping(required(document, "data", "response"), "response.data")

        pcb_minor = parse_money_minor(
            required(data, "price", "response.data"), "response.data.price"
        )
        shipping_minor, _shipping_method = self._pick_shipping(data)
        assembly_minor = 0
        if "assemblyPrice" in data and data["assemblyPrice"] is not None:
            assembly_minor = parse_money_minor(data["assemblyPrice"], "response.data.assemblyPrice")

        raw_total = data.get("totalPrice")
        if raw_total is None:
            total_minor = pcb_minor + shipping_minor + assembly_minor
        else:
            total_minor = parse_money_minor(raw_total, "response.data.totalPrice")

        currency = str(data.get("currency") or "USD").upper()
        lead_time_days = parse_lead_time_days(
            required(data, "leadTime", "response.data"), "response.data.leadTime"
        )
        if lead_time_days is None:
            raise VendorResponseError(
                "JLCPCB response did not include a lead time",
                evidence=[{"kind": "text", "message": "response.data.leadTime was empty"}],
            )

        breakdown: dict[str, int] = {"pcb": pcb_minor}
        if shipping_minor:
            breakdown["shipping"] = shipping_minor
        if assembly_minor:
            breakdown["assembly"] = assembly_minor

        url = data.get("url")
        if url is not None and not isinstance(url, str):
            raise VendorResponseError("malformed vendor response: response.data.url")
        if url is None:
            url = (
                "https://jlcpcb.com/quote"
                f"?layers={pcb.layers}&length={pcb.height_mm}"
                f"&width={pcb.width_mm}&qty={pcb.qty}"
            )

        return FabQuote(
            id=quote_id_for_spec(pcb, assembly),
            fab="jlcpcb",
            total_minor=total_minor,
            currency=currency,
            lead_time_days=lead_time_days,
            fetched_at=self._now(),
            breakdown=breakdown,
            url=url,
        )

    def _pick_shipping(self, data: Mapping[str, Any]) -> tuple[int, str | None]:
        raw = data.get("shippingOptions")
        if raw is None:
            return 0, None
        options = as_list(raw, "response.data.shippingOptions")
        if not options:
            return 0, None
        cheapest: tuple[int, str] | None = None
        for index, item in enumerate(options):
            entry = as_mapping(item, f"response.data.shippingOptions[{index}]")
            cost = parse_money_minor(
                required(entry, "cost", f"response.data.shippingOptions[{index}]"),
                f"response.data.shippingOptions[{index}].cost",
            )
            method = str(entry.get("shippingMethod") or f"option {index}")
            if cheapest is None or cost < cheapest[0]:
                cheapest = (cost, method)
        assert cheapest is not None
        return cheapest
