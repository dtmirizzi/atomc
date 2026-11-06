"""Extraction of IR ``/electrical`` data from ``ato build`` artifacts.

The atopile CLI writes a BOM (component metadata) and updates the project's ``.kicad_pcb``
(nets and pad connectivity). This module turns those artifacts into IR dictionaries. The
functions are pure so they can be tested against committed fixtures without running atopile.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .pcb import BoardModel, board_to_electrical

__all__ = [
    "assertions_from_variables",
    "components_from_bom",
    "extract_electrical",
    "merge_by_id",
]


def components_from_bom(bom: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Build ``comp:<designator>`` records from an atopile BOM document, keyed by id."""
    components: dict[str, dict[str, Any]] = {}
    raw_components = bom.get("components")
    if not isinstance(raw_components, list):
        return components
    for raw in raw_components:
        if not isinstance(raw, Mapping):
            continue
        usages = raw.get("usages")
        designators = _designators(usages)
        for designator in designators:
            components[f"comp:{designator}"] = {
                "id": f"comp:{designator}",
                "designator": designator,
                "mpn": _text(raw.get("mpn")),
                "manufacturer": _text(raw.get("manufacturer")),
                "value": _text(raw.get("value")),
                "description": _text(raw.get("description")),
                "package": _text(raw.get("package")),
                "lcsc": _text(raw.get("lcsc")),
                "dnp": False,
                "attributes": {},
                "pins": [],
            }
    return components


def assertions_from_variables(variables: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Map atopile variable specs (the result of ``assert ... within ...``) to assertions."""
    assertions: list[dict[str, Any]] = []
    nodes = variables.get("nodes")
    if not isinstance(nodes, list):
        return assertions
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        path = str(node.get("path") or node.get("name") or "")
        spec_variables = node.get("variables")
        if not isinstance(spec_variables, list):
            continue
        for variable in spec_variables:
            if not isinstance(variable, Mapping):
                continue
            spec = variable.get("spec")
            name = variable.get("name")
            if not spec or not name:
                continue
            meets = variable.get("meetsSpec")
            status = "pass" if meets is True else "fail" if meets is False else "unknown"
            slug = _slug(f"{path}_{name}")
            assertions.append(
                {
                    "id": f"assert:{slug}",
                    "expr": f"{path}.{name} within {spec}".strip(),
                    "status": status,
                }
            )
    return assertions


def extract_electrical(
    *,
    bom: Mapping[str, Any] | None,
    board: BoardModel | None,
    entry: str,
    variables: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Combine BOM metadata, board connectivity and variable specs into an ``/electrical`` node."""
    components = components_from_bom(bom or {})
    board_electrical = board_to_electrical(board) if board is not None else None
    if board_electrical is not None:
        for board_component in board_electrical["components"]:
            component_id = board_component["id"]
            target = components.get(component_id)
            if target is None:
                target = {
                    "id": component_id,
                    "designator": component_id.split(":", 1)[1],
                    "dnp": False,
                    "attributes": {},
                }
                components[component_id] = target
            target["pins"] = board_component["pins"]
        nets = board_electrical["nets"]
    else:
        nets = []
    return {
        "source": {"kind": "atopile", "entry": entry},
        "components": list(components.values()),
        "nets": nets,
        "assertions": assertions_from_variables(variables or {}),
    }


def merge_by_id(
    existing: list[dict[str, Any]] | None,
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Union two id-keyed lists, letting ``incoming`` win on id conflicts.

    The document has cross-node references into ``/electrical`` (firmware signals, sourcing BOM
    lines, mechanical bboxes), so replacing the node wholesale would strand references the
    plugin cannot see from its own write scope. Keeping existing entries preserves them.
    """
    merged: dict[str, dict[str, Any]] = {}
    for item in existing or []:
        item_id = item.get("id")
        if item_id:
            merged[str(item_id)] = item
    for item in incoming:
        item_id = item.get("id")
        if item_id:
            merged[str(item_id)] = item
    return list(merged.values())


def _designators(usages: Any) -> list[str]:
    if not isinstance(usages, list):
        return []
    out: list[str] = []
    for usage in usages:
        if isinstance(usage, Mapping):
            designator = usage.get("designator")
            if designator:
                out.append(str(designator))
    return out


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _slug(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "_.-" else "_" for ch in text)
    return cleaned.strip("_") or "unknown"
