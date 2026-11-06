"""Pure IR checks for the four atopile gates.

Every gate reads only IR data through the plugin context — no subprocess, no filesystem, no
network — so results are deterministic given the document revision. Handlers return a
:class:`~atomc_core_ir.GateResult`; the daemon overwrites ``id``/``plugin``/``severity``/
``owner_agent``/``ir_rev`` with manifest and store values.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from atomc_core_ir import GateResult

from .context import PluginContext
from .ir import read_value

__all__ = [
    "MIN_TEST_PADS",
    "check_assertions",
    "check_no_unconnected",
    "check_testpad_min_count",
    "check_testpad_nets_covered",
]

MIN_TEST_PADS = 8
"""Minimum number of bottom-side test pads the layout must expose to the pogo jig.

Covers VBUS, 3V3, GND, SWDIO, SWCLK, NRST, BOOT0 and at least one data net; the example boards
add every row/column net on top of that floor.
"""

_PLUGIN = "plugin:atopile"


def _result(
    gate_id: str,
    status: str,
    summary: str,
    *,
    evidence: list[dict[str, Any]] | None = None,
    refs: list[str] | None = None,
) -> GateResult:
    return GateResult(
        id=gate_id,
        status=status,
        plugin=_PLUGIN,
        evaluated_at=datetime.now(UTC),
        ir_rev=0,
        summary=summary,
        evidence=evidence or [],
        refs=refs or [],
    )


async def check_no_unconnected(ctx: PluginContext) -> GateResult:
    """``gate:erc.no_unconnected`` — every declared net connects at least two pins.

    A test pad counts as a connection: debug nets (SWD, UART, BOOT0) deliberately
    terminate on a single MCU pin plus a probe pad, and that is their purpose.
    A net is unconnected when it has fewer than two terminations (component pins
    + test pads).
    """
    electrical = await read_value(ctx, "/electrical")
    if not isinstance(electrical, Mapping):
        return _result(
            "gate:erc.no_unconnected",
            "SKIP",
            "/electrical is absent; nothing to check",
        )
    components = electrical.get("components") or []
    nets = electrical.get("nets") or []

    counts: Counter[str] = Counter()
    refs_by_net: dict[str, list[str]] = {}
    for component in components:
        if not isinstance(component, Mapping):
            continue
        component_id = str(component.get("id", "comp:?"))
        for pin in component.get("pins") or []:
            if not isinstance(pin, Mapping):
                continue
            net_ref = pin.get("net_ref")
            if not net_ref:
                continue
            net_ref = str(net_ref)
            counts[net_ref] += 1
            refs_by_net.setdefault(net_ref, []).append(f"{component_id}.{pin.get('number', '?')}")

    # Test pads terminate their nets deliberately: count them as connections.
    layout = await read_value(ctx, "/layout")
    test_pads = layout.get("test_pads") if isinstance(layout, Mapping) else None
    if isinstance(test_pads, list):
        for test_pad in test_pads:
            if not isinstance(test_pad, Mapping):
                continue
            net_ref = test_pad.get("net_ref")
            if net_ref:
                counts[str(net_ref)] += 1

    unconnected: list[str] = []
    for net in nets:
        if not isinstance(net, Mapping):
            continue
        net_ref = str(net.get("id", ""))
        if net_ref and counts.get(net_ref, 0) < 2:
            unconnected.append(net_ref)

    if not unconnected:
        return _result(
            "gate:erc.no_unconnected",
            "PASS",
            f"{len(nets)} nets each connect >= 2 pins",
            evidence=[{"kind": "json", "data": {"nets": len(nets), "unconnected": []}}],
        )
    # Document referential integrity requires refs to resolve to declared ids:
    # pin-level refs ("comp:U1.5") are not ids, so they carry in the evidence
    # detail and the refs list the unconnected nets (which are ids) instead.
    return _result(
        "gate:erc.no_unconnected",
        "FAIL",
        f"{len(unconnected)} net(s) have fewer than 2 connected pins",
        evidence=[
            {
                "kind": "json",
                "data": {
                    "unconnected": [
                        {
                            "net": net_ref,
                            "pins": counts.get(net_ref, 0),
                            "pin_refs": refs_by_net.get(net_ref, []),
                        }
                        for net_ref in unconnected
                    ]
                },
            }
        ],
        refs=unconnected,
    )


async def check_assertions(ctx: PluginContext) -> GateResult:
    """``gate:erc.assertions`` — every recorded atopile assertion passes."""
    electrical = await read_value(ctx, "/electrical")
    if not isinstance(electrical, Mapping):
        return _result(
            "gate:erc.assertions",
            "SKIP",
            "/electrical is absent; nothing to check",
        )
    assertions = electrical.get("assertions") or []
    statuses = [
        str(assertion.get("status", "unknown"))
        for assertion in assertions
        if isinstance(assertion, Mapping)
    ]
    if not statuses:
        return _result("gate:erc.assertions", "SKIP", "no assertions recorded")

    failed = [
        str(assertion.get("id", "assert:?"))
        for assertion in assertions
        if isinstance(assertion, Mapping) and assertion.get("status") == "fail"
    ]
    if failed:
        return _result(
            "gate:erc.assertions",
            "FAIL",
            f"{len(failed)} assertion(s) failed",
            evidence=[{"kind": "json", "data": {"failed": failed}}],
            refs=failed,
        )
    if "unknown" in statuses:
        unknown = [
            str(assertion.get("id", "assert:?"))
            for assertion in assertions
            if isinstance(assertion, Mapping) and assertion.get("status") == "unknown"
        ]
        return _result(
            "gate:erc.assertions",
            "SKIP",
            f"{len(unknown)} assertion(s) have unknown status",
            evidence=[{"kind": "json", "data": {"unknown": unknown}}],
            refs=unknown,
        )
    return _result(
        "gate:erc.assertions",
        "PASS",
        f"{len(statuses)} assertion(s) passed",
    )


async def check_testpad_min_count(ctx: PluginContext) -> GateResult:
    """``gate:layout.testpads.min_count`` — at least :data:`MIN_TEST_PADS` test pads exist."""
    layout = await read_value(ctx, "/layout")
    if not isinstance(layout, Mapping):
        return _result(
            "gate:layout.testpads.min_count",
            "SKIP",
            "/layout is absent; nothing to check",
        )
    test_pads = [p for p in layout.get("test_pads") or [] if isinstance(p, Mapping)]
    count = len(test_pads)
    if count >= MIN_TEST_PADS:
        return _result(
            "gate:layout.testpads.min_count",
            "PASS",
            f"{count} test pads (>= {MIN_TEST_PADS})",
            evidence=[{"kind": "json", "data": {"count": count, "minimum": MIN_TEST_PADS}}],
        )
    return _result(
        "gate:layout.testpads.min_count",
        "FAIL",
        f"{count} test pads (< {MIN_TEST_PADS})",
        evidence=[{"kind": "json", "data": {"count": count, "minimum": MIN_TEST_PADS}}],
        refs=[str(p.get("id", "")) for p in test_pads],
    )


async def check_testpad_nets_covered(ctx: PluginContext) -> GateResult:
    """``gate:layout.testpads.nets_covered`` — every matrix net has a test pad."""
    layout = await read_value(ctx, "/layout")
    keyboard = await read_value(ctx, "/keyboard")
    electrical = await read_value(ctx, "/electrical")
    if not isinstance(layout, Mapping):
        return _result(
            "gate:layout.testpads.nets_covered",
            "SKIP",
            "/layout is absent; nothing to check",
        )
    if not isinstance(keyboard, Mapping):
        return _result(
            "gate:layout.testpads.nets_covered",
            "SKIP",
            "/keyboard is absent; matrix nets are unknown",
        )
    if not isinstance(electrical, Mapping):
        return _result(
            "gate:layout.testpads.nets_covered",
            "SKIP",
            "/electrical is absent; matrix nets are unknown",
        )

    components = {
        str(component.get("id")): component
        for component in electrical.get("components") or []
        if isinstance(component, Mapping) and component.get("id")
    }
    required: set[str] = set()
    for key in keyboard.get("keys") or []:
        if not isinstance(key, Mapping):
            continue
        for field in ("switch_ref", "diode_ref"):
            component = components.get(str(key.get(field)))
            if component is None:
                continue
            for pin in component.get("pins") or []:
                if isinstance(pin, Mapping) and pin.get("net_ref"):
                    required.add(str(pin["net_ref"]))

    if not required:
        return _result(
            "gate:layout.testpads.nets_covered",
            "SKIP",
            "no matrix nets could be resolved from /keyboard + /electrical",
        )

    covered = {
        str(pad.get("net_ref"))
        for pad in layout.get("test_pads") or []
        if isinstance(pad, Mapping) and pad.get("net_ref")
    }
    missing = sorted(required - covered)
    if missing:
        return _result(
            "gate:layout.testpads.nets_covered",
            "FAIL",
            f"{len(missing)} matrix net(s) lack a test pad",
            evidence=[{"kind": "json", "data": {"missing": missing, "required": sorted(required)}}],
            refs=missing,
        )
    return _result(
        "gate:layout.testpads.nets_covered",
        "PASS",
        f"all {len(required)} matrix nets are covered",
        evidence=[{"kind": "json", "data": {"required": sorted(required)}}],
    )
