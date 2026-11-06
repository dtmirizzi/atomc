"""Adapter interface shared by fabrication-quote integrations.

A fabrication adapter is not a parts adapter: it quotes a :class:`~atomc_core_ir.PcbSpec`
(plus an optional assembly request) rather than a component. The honesty contract is the same as
in :mod:`atomc_plugin_sourcing.adapters.base`: missing credentials or an unreachable endpoint
becomes ``UNAVAILABLE``, a malformed response becomes ``ERROR``, and neither path can produce a
partial :class:`~atomc_core_ir.FabQuote`. Tests inject an ``httpx.BaseTransport`` so no test
opens a socket, and no live vendor call is made while developing this package.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Literal

import httpx
from atomc_core_ir import Assembly, FabQuote, PcbSpec

from ..errors import VendorResponseError, VendorUnavailableError
from ..models import format_timestamp, utcnow

__all__ = ["FabAdapter", "FabAdapterStatus", "FabQuoteResult"]

_MAX_BODY_EVIDENCE = 800

FabAdapterStatus = Literal["OK", "UNAVAILABLE", "ERROR"]


@dataclass(frozen=True, slots=True)
class FabQuoteResult:
    """Outcome of one fabrication-quote request.

    ``OK`` carries exactly one :class:`~atomc_core_ir.FabQuote`. ``UNAVAILABLE`` means no live
    data could be obtained (missing credentials, unreachable endpoint, rejected auth).
    ``ERROR`` means a response arrived but was malformed. Neither failure status ever carries a
    quote.
    """

    fab: str
    status: FabAdapterStatus
    quote: FabQuote | None = None
    message: str | None = None
    evidence: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    fetched_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if self.status == "OK" and self.quote is None:
            raise ValueError("an OK fabrication result must carry a quote")
        if self.status != "OK" and self.quote is not None:
            raise ValueError("a failed fabrication result must not carry a quote")

    def to_dict(self) -> dict[str, Any]:
        return {
            "fab": self.fab,
            "status": self.status,
            "message": self.message,
            "evidence": list(self.evidence),
            "fetched_at": format_timestamp(self.fetched_at),
            "quote": self.quote.model_dump(mode="json") if self.quote is not None else None,
        }


class FabAdapter(ABC):
    """Base class for a fabrication-quote adapter with honest outcomes."""

    fab: ClassVar[str]
    display_name: ClassVar[str]
    default_endpoint: ClassVar[str]
    env_keys: ClassVar[tuple[str, ...]] = ()

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        env: Mapping[str, str] | None = None,
        clock: Callable[[], datetime] | None = None,
        timeout_s: float = 15.0,
        endpoint: str | None = None,
    ) -> None:
        self._transport = transport
        self._env: Mapping[str, str] = env if env is not None else {}
        self._clock = clock or utcnow
        self._timeout_s = timeout_s
        self._endpoint = (endpoint or self.default_endpoint).rstrip("/")

    # -- public API ---------------------------------------------------------

    def quote(self, pcb: PcbSpec, assembly: Assembly | None = None) -> FabQuoteResult:
        """Run one quote and normalize every failure into a :class:`FabQuoteResult`."""
        fetched_at = self._clock()
        try:
            quote = self.quote_pcb(pcb, assembly)
        except VendorUnavailableError as exc:
            return FabQuoteResult(
                fab=self.fab,
                status="UNAVAILABLE",
                message=exc.message,
                evidence=tuple(exc.evidence),
                fetched_at=fetched_at,
            )
        except VendorResponseError as exc:
            return FabQuoteResult(
                fab=self.fab,
                status="ERROR",
                message=exc.message,
                evidence=tuple(exc.evidence),
                fetched_at=fetched_at,
            )
        except Exception as exc:
            return FabQuoteResult(
                fab=self.fab,
                status="ERROR",
                message=f"adapter raised {type(exc).__name__}: {exc}",
                evidence=(
                    {
                        "kind": "text",
                        "message": "unexpected adapter failure; no quote was produced",
                    },
                ),
                fetched_at=fetched_at,
            )
        return FabQuoteResult(
            fab=self.fab,
            status="OK",
            quote=quote,
            fetched_at=fetched_at,
            evidence=(
                {
                    "kind": "text",
                    "message": (
                        f"{self.display_name} quote parsed; total {quote.total_minor} "
                        f"{quote.currency} minor units"
                    ),
                },
            ),
        )

    @abstractmethod
    def quote_pcb(self, pcb: PcbSpec, assembly: Assembly | None = None) -> FabQuote:
        """Return a validated quote or raise a typed unavailable/response error."""

    # -- helpers ------------------------------------------------------------

    def _now(self) -> datetime:
        return self._clock()

    def _env_value(self, name: str) -> str | None:
        value = self._env.get(name)
        if value is None:
            return None
        value = value.strip()
        return value or None

    def _require_env(self, *names: str) -> dict[str, str]:
        values: dict[str, str] = {}
        missing: list[str] = []
        for name in names:
            value = self._env_value(name)
            if value is None:
                missing.append(name)
            else:
                values[name] = value
        if missing:
            raise VendorUnavailableError(
                f"{self.display_name} requires credentials in {' and '.join(missing)}; "
                "no live call was made",
                evidence=[
                    {
                        "kind": "text",
                        "message": (
                            f"missing required environment variable(s): {', '.join(missing)}"
                        ),
                    }
                ],
            )
        return values

    def _client(self) -> httpx.Client:
        return httpx.Client(transport=self._transport, timeout=self._timeout_s)

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        content: str,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        """Perform one request and return decoded JSON, mapping transport/status failures."""
        url = self._endpoint + path
        try:
            with self._client() as client:
                response = client.request(method, url, content=content, headers=headers)
        except httpx.HTTPError as exc:
            raise VendorUnavailableError(
                f"{self.display_name} endpoint unreachable: {type(exc).__name__}",
                evidence=[
                    {
                        "kind": "text",
                        "message": (
                            f"{method} {url} failed with {type(exc).__name__}; no quote "
                            "was synthesized"
                        ),
                    }
                ],
            ) from exc

        if response.status_code in {401, 403}:
            raise VendorUnavailableError(
                f"{self.display_name} rejected the supplied credentials (HTTP "
                f"{response.status_code})",
                evidence=[
                    {
                        "kind": "text",
                        "message": (
                            f"HTTP {response.status_code} from {url}; check the vendor API "
                            "app id/access key"
                        ),
                    }
                ],
            )
        if response.status_code == 429 or response.status_code >= 500:
            raise VendorUnavailableError(
                f"{self.display_name} endpoint unavailable (HTTP {response.status_code})",
                evidence=[
                    {
                        "kind": "text",
                        "message": f"HTTP {response.status_code} from {url}; retry later",
                    }
                ],
            )
        if response.status_code >= 400:
            raise VendorResponseError(
                f"{self.display_name} returned HTTP {response.status_code}",
                evidence=[
                    {"kind": "text", "message": self._body_evidence(response)},
                ],
            )

        try:
            return response.json()
        except ValueError as exc:
            raise VendorResponseError(
                f"{self.display_name} returned non-JSON content",
                evidence=[{"kind": "text", "message": self._body_evidence(response)}],
            ) from exc

    @staticmethod
    def _body_evidence(response: httpx.Response) -> str:
        text = response.text.replace("\n", " ").strip()
        if len(text) > _MAX_BODY_EVIDENCE:
            text = text[:_MAX_BODY_EVIDENCE] + "...[truncated]"
        return f"HTTP {response.status_code}: {text or '<empty body>'}"
