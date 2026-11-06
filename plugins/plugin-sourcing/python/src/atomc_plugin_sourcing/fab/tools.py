"""The ``fab.quote_pcb`` tool implementation.

Fetches PCB fabrication quotes for a spec and writes them into ``/fabrication/quotes`` through the
injected plugin context. The spec is taken from the tool payload, then from an existing
``/fabrication/pcb``, otherwise derived from ``/layout`` with documented defaults. Nothing here
invents prices: every ``FabQuote`` comes from a parsed adapter response. When no trustworthy
quote is available the tool returns an honest ``UNAVAILABLE``/``ERROR`` and leaves the IR
untouched.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any

from atomc_core_ir import Assembly, FabQuote, PcbSpec

from ..errors import SourcingQueryError
from .service import FabService
from .spec import assembly_from_mapping, pcb_spec_for_ir, spec_from_mapping

__all__ = ["quote_pcb_payload", "tool_error"]

_SUPPORTED_FABS = ("jlcpcb",)


def tool_error(message: str, *, evidence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build an honest tool failure result (never PASS, never a fabricated quote)."""
    return {
        "status": "ERROR",
        "summary": message,
        "evidence": evidence or [{"kind": "text", "message": message}],
        "quotes": [],
    }


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _node_rev(existing: Mapping[str, Any] | None) -> int:
    """Return the ``_meta.rev`` of an existing node, or 0 when it is absent."""
    if not isinstance(existing, Mapping):
        return 0
    meta = existing.get("_meta")
    if isinstance(meta, Mapping):
        rev = meta.get("rev")
        if isinstance(rev, int) and not isinstance(rev, bool):
            return rev
    return 0


def _payload_mapping(payload: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise SourcingQueryError("tool payload must be an object")
    return payload


def _optional_bool(payload: Mapping[str, Any], key: str, default: bool) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise SourcingQueryError(f"'{key}' must be a boolean")
    return value


def _fabs(payload: Mapping[str, Any]) -> tuple[str, ...] | None:
    value = payload.get("fabs")
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SourcingQueryError("'fabs' must be an array of fab names")
    selected: list[str] = []
    for fab in value:
        if fab not in _SUPPORTED_FABS:
            raise SourcingQueryError(
                f"unknown fab {fab!r}; supported: {', '.join(_SUPPORTED_FABS)}"
            )
        if fab not in selected:
            selected.append(fab)
    if not selected:
        raise SourcingQueryError("'fabs' must not be empty")
    return tuple(selected)


def _resolve_spec(
    document: Mapping[str, Any],
    payload: Mapping[str, Any],
    existing: Mapping[str, Any] | None,
) -> tuple[PcbSpec, Assembly | None, list[str]]:
    """Return ``(pcb, assembly, evidence)`` from payload, existing node, or the IR layout."""
    evidence: list[str] = []
    raw_pcb = payload.get("pcb")
    if raw_pcb is not None:
        if not isinstance(raw_pcb, Mapping):
            raise SourcingQueryError("'pcb' must be an object")
        try:
            pcb = spec_from_mapping(raw_pcb)
        except ValueError as exc:
            raise SourcingQueryError(f"invalid 'pcb' spec: {exc}") from exc
        evidence.append("pcb spec taken from the tool payload")
    elif existing is not None and isinstance(existing.get("pcb"), Mapping):
        pcb = spec_from_mapping(existing["pcb"])
        evidence.append("pcb spec taken from /fabrication/pcb")
    else:
        pcb, derived = pcb_spec_for_ir(document)
        evidence.extend(derived)

    if "assembly" in payload:
        raw_assembly = payload.get("assembly")
        if raw_assembly is not None and not isinstance(raw_assembly, Mapping):
            raise SourcingQueryError("'assembly' must be an object or null")
        try:
            assembly = assembly_from_mapping(raw_assembly)
        except ValueError as exc:
            raise SourcingQueryError(f"invalid 'assembly': {exc}") from exc
        evidence.append("assembly taken from the tool payload")
    else:
        raw_existing = existing.get("assembly") if isinstance(existing, Mapping) else None
        assembly = (
            assembly_from_mapping(raw_existing) if isinstance(raw_existing, Mapping) else None
        )
    return pcb, assembly, evidence


def _write_ops(
    *,
    existing: Mapping[str, Any] | None,
    pcb: PcbSpec,
    assembly: Assembly | None,
    quotes: list[FabQuote],
) -> list[dict[str, Any]]:
    pcb_value = pcb.model_dump(mode="json")
    assembly_value = assembly.model_dump(mode="json") if assembly is not None else None
    if existing is None:
        node: dict[str, Any] = {
            "_meta": {"rev": 0, "lock": None},
            "pcb": pcb_value,
            "quotes": [quote.model_dump(mode="json") for quote in quotes],
        }
        if assembly_value is not None:
            node["assembly"] = assembly_value
        return [{"op": "add", "path": "", "value": node}]

    existing_quotes = existing.get("quotes")
    kept: list[Any] = []
    if isinstance(existing_quotes, list):
        new_ids = {quote.id for quote in quotes}
        kept = [
            item
            for item in existing_quotes
            if isinstance(item, Mapping) and item.get("id") not in new_ids
        ]
    merged = kept + [quote.model_dump(mode="json") for quote in quotes]
    ops: list[dict[str, Any]] = [
        {"op": "replace", "path": "/pcb", "value": pcb_value},
        {"op": "add", "path": "/assembly", "value": assembly_value},
        {"op": "replace", "path": "/quotes", "value": merged},
    ]
    return ops


async def quote_pcb_payload(
    service: FabService,
    ctx: Any,
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Implementation of the mutating ``quote_pcb`` tool."""
    try:
        args = _payload_mapping(payload)
        fabs = _fabs(args)
        write = _optional_bool(args, "write", True)
        force = _optional_bool(args, "force", False)
    except SourcingQueryError as exc:
        return tool_error(str(exc))

    getter = getattr(ctx, "ir_get", None)
    if not callable(getter):
        return tool_error("plugin context does not expose IR reads")
    try:
        document = await _maybe_await(getter("/"))
    except Exception as exc:
        return tool_error(f"failed to read the IR root: {type(exc).__name__}: {exc}")
    if not isinstance(document, Mapping):
        return tool_error("IR root is not an object")
    existing = document.get("fabrication")
    if existing is not None and not isinstance(existing, Mapping):
        return tool_error("/fabrication is not an object")
    existing_mapping = existing if isinstance(existing, Mapping) else None
    rev = _node_rev(existing_mapping)

    try:
        pcb, assembly, evidence = _resolve_spec(document, args, existing_mapping)
    except SourcingQueryError as exc:
        return tool_error(str(exc))
    except ValueError as exc:
        return tool_error(str(exc))

    report = service.quote(pcb, assembly, fabs=fabs, force=force)
    evidence = [*evidence, *[f"fab {r.fab}: {r.status}" for r in report.results]]
    if not report.quotes:
        return {
            "status": report.status,
            "summary": report.summary,
            "pcb": pcb.model_dump(mode="json"),
            "assembly": assembly.model_dump(mode="json") if assembly else None,
            "quotes": [],
            "fabs": [result.to_dict() for result in report.results],
            "evidence": [{"kind": "text", "message": message} for message in evidence],
        }

    quotes = list(report.quotes)
    new_rev: int | None = None
    if write:
        ops = _write_ops(existing=existing_mapping, pcb=pcb, assembly=assembly, quotes=quotes)
        try:
            outcome = await _maybe_await(ctx.ir_transact("/fabrication", rev, ops))
        except Exception as exc:
            return tool_error(
                f"failed to write quotes into /fabrication: {type(exc).__name__}: {exc}",
                evidence=[
                    {"kind": "text", "message": "no quotes were written to the IR"},
                    {"kind": "text", "message": "quote fetch succeeded but the write failed"},
                ],
            )
        raw_new_rev = getattr(outcome, "new_rev", None)
        if raw_new_rev is None and isinstance(outcome, Mapping):
            raw_new_rev = outcome.get("new_rev")
        if isinstance(raw_new_rev, int) and not isinstance(raw_new_rev, bool):
            new_rev = raw_new_rev

    return {
        "status": "UPDATED" if write else "OK",
        "summary": (
            f"fetched {len(quotes)} fab quote(s) and wrote /fabrication"
            if write
            else f"fetched {len(quotes)} fab quote(s); write=false so the IR was left unchanged"
        ),
        "pcb": pcb.model_dump(mode="json"),
        "assembly": assembly.model_dump(mode="json") if assembly else None,
        "quotes": [quote.model_dump(mode="json") for quote in quotes],
        "quotes_written": len(quotes) if write else 0,
        "new_rev": new_rev,
        "fabs": [result.to_dict() for result in report.results],
        "evidence": [{"kind": "text", "message": message} for message in evidence],
    }
