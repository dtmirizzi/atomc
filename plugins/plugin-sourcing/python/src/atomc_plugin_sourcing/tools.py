"""The ``sourcing:query`` and ``sourcing:refresh`` tool implementations.

Both handlers surface every vendor outcome. ``query`` is read-only; ``refresh`` writes only
``/sourcing`` through the injected context transaction, and only when at least one attempted line
produced a trustworthy authoritative result. Nothing here invents stock or prices: every offer
comes from a parsed vendor response or a TTL cache entry derived from one.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from typing import Any

from atomc_core_ir import Offer

from .adapters import DEFAULT_VENDORS
from .errors import NormalizationError, SourcingQueryError
from .models import AdapterResult, ComponentQuery, VendorOffer
from .normalize import to_ir_offers
from .service import QueryReport, SourcingService

__all__ = ["query_payload", "refresh_payload", "tool_error"]

_SUPPORTED_VENDORS = frozenset(DEFAULT_VENDORS)


def tool_error(message: str, *, evidence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build an honest tool failure result (never PASS, never fabricated data)."""
    return {
        "status": "ERROR",
        "available": False,
        "summary": message,
        "evidence": evidence or [{"kind": "text", "message": message}],
    }


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _read_node(ctx: Any, path: str) -> tuple[int, Any]:
    reader = getattr(ctx, "ir_read", None)
    if callable(reader):
        payload = await _maybe_await(reader(path))
        if isinstance(payload, Mapping) and "value" in payload:
            rev = payload.get("rev", 0)
            try:
                return int(rev), payload["value"]
            except TypeError, ValueError:
                return 0, payload["value"]
    getter = getattr(ctx, "ir_get", None)
    if not callable(getter):
        raise SourcingQueryError("plugin context does not expose IR reads")
    return 0, await _maybe_await(getter(path))


def _payload_mapping(payload: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise SourcingQueryError("tool payload must be an object")
    return payload


def _optional_str(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise SourcingQueryError(f"'{key}' must be a string")
    value = value.strip()
    return value or None


def _optional_bool(payload: Mapping[str, Any], key: str, default: bool = False) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise SourcingQueryError(f"'{key}' must be a boolean")
    return value


def _optional_ttl(payload: Mapping[str, Any]) -> int | None:
    value = payload.get("ttl_s")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SourcingQueryError("'ttl_s' must be a non-negative integer")
    return value


def _vendors(payload: Mapping[str, Any]) -> tuple[str, ...] | None:
    value = payload.get("vendors")
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SourcingQueryError("'vendors' must be an array of vendor names")
    selected: list[str] = []
    for vendor in value:
        if vendor not in _SUPPORTED_VENDORS:
            raise SourcingQueryError(
                f"unknown vendor {vendor!r}; supported: {', '.join(DEFAULT_VENDORS)}"
            )
        if vendor not in selected:
            selected.append(vendor)
    if not selected:
        raise SourcingQueryError("'vendors' must not be empty")
    return tuple(selected)


def _line_identifiers(line: Mapping[str, Any]) -> tuple[str | None, str | None]:
    mpn = line.get("mpn")
    lcsc = line.get("lcsc")
    if mpn is not None and not isinstance(mpn, str):
        raise SourcingQueryError("BOM line 'mpn' must be a string")
    if lcsc is not None and not isinstance(lcsc, str):
        raise SourcingQueryError("BOM line 'lcsc' must be a string")
    return (mpn.strip() or None if mpn else None), (lcsc.strip() or None if lcsc else None)


async def _query_from_payload(ctx: Any, payload: Mapping[str, Any]) -> tuple[ComponentQuery, str]:
    mpn = _optional_str(payload, "mpn")
    lcsc = _optional_str(payload, "lcsc")
    qty = 1
    bom_line_id = _optional_str(payload, "bom_line_id")
    if bom_line_id is not None:
        _rev, node = await _read_node(ctx, "/sourcing")
        if not isinstance(node, Mapping):
            raise SourcingQueryError(
                f"bom_line_id {bom_line_id!r} was requested but /sourcing is absent"
            )
        bom = node.get("bom")
        if not isinstance(bom, list):
            raise SourcingQueryError("/sourcing has no BOM array")
        line = next(
            (item for item in bom if isinstance(item, Mapping) and item.get("id") == bom_line_id),
            None,
        )
        if line is None:
            raise SourcingQueryError(f"BOM line {bom_line_id!r} not found in /sourcing")
        line_mpn, line_lcsc = _line_identifiers(line)
        mpn = mpn or line_mpn
        lcsc = lcsc or line_lcsc
        raw_qty = line.get("qty_per_unit", 1)
        if isinstance(raw_qty, int) and not isinstance(raw_qty, bool) and raw_qty >= 1:
            qty = raw_qty
    if not mpn and not lcsc:
        raise SourcingQueryError("provide 'bom_line_id', 'mpn' or 'lcsc'")
    return ComponentQuery(mpn=mpn, lcsc=lcsc, qty=qty), bom_line_id or lcsc or mpn or "query"


def _normalized_offers(report: QueryReport, prefix: str) -> list[dict[str, Any]]:
    """Normalize offers and attach the adapter/cache provenance for the tool report."""
    pairs: list[tuple[AdapterResult, VendorOffer]] = [
        (result, offer) for result in report.results for offer in result.offers
    ]
    ir_offers: list[Offer] = to_ir_offers((offer for _result, offer in pairs), prefix)
    normalized: list[dict[str, Any]] = []
    for ir_offer, (result, offer) in zip(ir_offers, pairs, strict=True):
        entry = ir_offer.model_dump(mode="json")
        entry["adapter_vendor"] = result.vendor
        entry["cached"] = result.cached
        entry["mpn"] = offer.mpn
        normalized.append(entry)
    return normalized


async def query_payload(
    service: SourcingService,
    ctx: Any,
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Implementation of the read-only ``query`` tool."""
    try:
        args = _payload_mapping(payload)
        query, prefix = await _query_from_payload(ctx, args)
        vendors = _vendors(args)
        force = _optional_bool(args, "force")
        ttl_s = _optional_ttl(args)
        report = service.query(query, vendors=vendors, force=force, ttl_s=ttl_s)
        normalized = _normalized_offers(report, prefix)
    except SourcingQueryError as exc:
        return tool_error(str(exc))
    except NormalizationError as exc:
        return tool_error(f"vendor offer normalization failed: {exc}")
    except ValueError as exc:
        return tool_error(str(exc))

    result = report.to_dict()
    result["offers"] = normalized
    return result


def _refresh_ops(
    updates: Sequence[tuple[int, Mapping[str, Any], list[Offer]]],
) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []
    for index, line, offers in updates:
        chosen_old = line.get("chosen_offer_ref")
        new_ids = {offer.id for offer in offers}
        chosen = chosen_old if chosen_old in new_ids else None
        ops.append(
            {
                "op": "add",
                "path": f"/bom/{index}/offers",
                "value": [offer.model_dump(mode="json") for offer in offers],
            }
        )
        ops.append(
            {
                "op": "add",
                "path": f"/bom/{index}/chosen_offer_ref",
                "value": chosen,
            }
        )
    return ops


async def refresh_payload(
    service: SourcingService,
    ctx: Any,
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Implementation of the mutating ``refresh`` tool."""
    try:
        args = _payload_mapping(payload)
        vendors = _vendors(args)
        force = _optional_bool(args, "force")
        ttl_s = _optional_ttl(args)
    except SourcingQueryError as exc:
        return tool_error(str(exc))

    try:
        rev, node = await _read_node(ctx, "/sourcing")
    except SourcingQueryError as exc:
        return tool_error(str(exc))
    if not isinstance(node, Mapping):
        return {
            "status": "SKIP",
            "available": False,
            "summary": "/sourcing is absent; nothing to refresh",
            "evidence": [{"kind": "text", "message": "no /sourcing node was read"}],
        }
    bom = node.get("bom")
    if not isinstance(bom, list):
        return {
            "status": "SKIP",
            "available": False,
            "summary": "/sourcing has no BOM array; nothing to refresh",
            "evidence": [{"kind": "text", "message": "expected /sourcing/bom to be an array"}],
        }

    updates: list[tuple[int, Mapping[str, Any], list[Offer]]] = []
    line_results: list[dict[str, Any]] = []
    attempted = 0
    offers_written = 0
    try:
        for index, raw_line in enumerate(bom):
            if not isinstance(raw_line, Mapping):
                raise SourcingQueryError(f"/sourcing/bom[{index}] is not an object")
            line = raw_line
            line_id = str(line.get("id") or f"bom:{index}")
            mpn, lcsc = _line_identifiers(line)
            if not mpn and not lcsc:
                line_results.append(
                    {
                        "bom_line_id": line_id,
                        "status": "SKIP",
                        "summary": "no mpn or lcsc on this BOM line",
                        "offers": 0,
                    }
                )
                continue
            raw_qty = line.get("qty_per_unit", 1)
            qty = raw_qty if isinstance(raw_qty, int) and not isinstance(raw_qty, bool) else 1
            query = ComponentQuery(mpn=mpn, lcsc=lcsc, qty=max(qty, 1))
            attempted += 1
            report = service.query(query, vendors=vendors, force=force, ttl_s=ttl_s)
            normalized = to_ir_offers(report.offers, line_id)
            all_ok = all(result.status == "OK" for result in report.results)
            if normalized or all_ok:
                updates.append((index, line, normalized))
            offers_written += len(normalized)
            line_results.append(
                {
                    "bom_line_id": line_id,
                    "status": report.status,
                    "summary": report.summary,
                    "offers": len(normalized),
                    "cached_vendors": [result.vendor for result in report.results if result.cached],
                    "vendors": [
                        {
                            "vendor": result.vendor,
                            "status": result.status,
                            "cached": result.cached,
                            "message": result.message,
                        }
                        for result in report.results
                    ],
                }
            )
    except (SourcingQueryError, NormalizationError, ValueError) as exc:
        return tool_error(str(exc))

    if not updates:
        status = "UNAVAILABLE" if attempted else "SKIP"
        return {
            "status": status,
            "available": False,
            "summary": (
                "no trustworthy vendor data was available; /sourcing was left unchanged"
                if attempted
                else "no refreshable BOM lines"
            ),
            "attempted_lines": attempted,
            "line_results": line_results,
            "evidence": [
                {
                    "kind": "text",
                    "message": (
                        "missing credentials, unreachable endpoints or malformed responses; "
                        "no offers were written"
                    ),
                }
            ],
        }

    ops = _refresh_ops(updates)
    outcome = await _maybe_await(ctx.ir_transact("/sourcing", rev, ops))
    new_rev = getattr(outcome, "new_rev", None)
    if new_rev is None and isinstance(outcome, Mapping):
        new_rev = outcome.get("new_rev")
    return {
        "status": "UPDATED",
        "available": offers_written > 0,
        "summary": (f"refreshed {len(updates)} BOM line(s) with {offers_written} vendor offer(s)"),
        "updated_lines": len(updates),
        "offers_written": offers_written,
        "attempted_lines": attempted,
        "new_rev": new_rev,
        "line_results": line_results,
    }
