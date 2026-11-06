"""Adapter interface shared by every vendor integration.

Each vendor module implements :meth:`VendorAdapter.query_component` against that vendor's
documented public response shape. The base class owns the honest outcome contract: a missing
API key or unreachable endpoint becomes ``UNAVAILABLE``, a malformed response becomes
``ERROR``, and neither path can return a partial offer list. Tests inject an
``httpx.BaseTransport`` (for example ``httpx.MockTransport``) so no test opens a socket.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, ClassVar

import httpx

from ..errors import VendorResponseError, VendorUnavailableError
from ..models import AdapterResult, ComponentQuery, VendorOffer, utcnow

__all__ = ["VendorAdapter"]

_MAX_BODY_EVIDENCE = 800


class VendorAdapter(ABC):
    """Base class for a keyless-or-keyed vendor adapter."""

    vendor: ClassVar[str]
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

    def query(self, query: ComponentQuery) -> AdapterResult:
        """Run one query and normalize every failure into an :class:`AdapterResult`."""
        fetched_at = self._clock()
        try:
            offers = self.query_component(query)
        except VendorUnavailableError as exc:
            return AdapterResult(
                vendor=self.vendor,
                status="UNAVAILABLE",
                message=exc.message,
                evidence=tuple(exc.evidence),
                fetched_at=fetched_at,
            )
        except VendorResponseError as exc:
            return AdapterResult(
                vendor=self.vendor,
                status="ERROR",
                message=exc.message,
                evidence=tuple(exc.evidence),
                fetched_at=fetched_at,
            )
        except Exception as exc:
            return AdapterResult(
                vendor=self.vendor,
                status="ERROR",
                message=f"adapter raised {type(exc).__name__}: {exc}",
                evidence=(
                    {
                        "kind": "text",
                        "message": "unexpected adapter failure; no offers were produced",
                    },
                ),
                fetched_at=fetched_at,
            )
        return AdapterResult(
            vendor=self.vendor,
            status="OK",
            offers=tuple(offers),
            fetched_at=fetched_at,
            evidence=(
                {
                    "kind": "text",
                    "message": f"{self.display_name} response parsed ({len(offers)} offers)",
                },
            ),
        )

    @abstractmethod
    def query_component(self, query: ComponentQuery) -> list[VendorOffer]:
        """Return parsed offers or raise a typed unavailable/response error."""

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
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        """Perform one request and return decoded JSON, mapping transport/status failures."""
        url = self._endpoint + path
        try:
            with self._client() as client:
                response = client.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise VendorUnavailableError(
                f"{self.display_name} endpoint unreachable: {type(exc).__name__}",
                evidence=[
                    {
                        "kind": "text",
                        "message": (
                            f"{method} {url} failed with {type(exc).__name__}; no offers "
                            "were synthesized"
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
                            "key/scope"
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
                    {
                        "kind": "text",
                        "message": self._body_evidence(response),
                    }
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
