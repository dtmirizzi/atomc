"""KiCad ``.kicad_pcb`` parsing and mapping onto IR layout/electrical data.

``kiutils`` is imported lazily so the plugin can be installed and unit-tested without it; every
entry point raises :class:`~atomc_plugin_atopile.errors.KiutilsUnavailableError` instead of
importing at module scope. The mapping from a :class:`BoardModel` to IR dictionaries is pure and
tested independently of kiutils.
"""

from __future__ import annotations

import importlib
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import BoardParseError, KiutilsUnavailableError

__all__ = [
    "BoardModel",
    "FootprintModel",
    "PadModel",
    "board_to_electrical",
    "board_to_layout",
    "load_board",
    "net_id",
]


@dataclass(frozen=True, slots=True)
class PadModel:
    """One pad on a footprint, with its absolute board coordinates."""

    number: str
    net_name: str | None
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class FootprintModel:
    """A footprint placed on the board."""

    reference: str | None
    lib_id: str
    value: str | None
    mpn: str | None
    x: float
    y: float
    rotation_deg: float
    side: str
    pads: tuple[PadModel, ...] = ()


@dataclass(frozen=True, slots=True)
class BoardModel:
    """The subset of a ``.kicad_pcb`` the plugin needs."""

    path: str
    thickness_mm: float
    layers: int
    outline: tuple[tuple[float, float], ...]
    footprints: tuple[FootprintModel, ...] = ()
    nets: Mapping[str, str] = field(default_factory=dict)


def net_id(name: str) -> str | None:
    """Map a KiCad net name to an IR id, or ``None`` when it is empty/unnamed."""
    cleaned = "".join(ch for ch in name if ch.isalnum() or ch in "_.-/")
    if not cleaned:
        return None
    return f"net:{cleaned}"


# ---------------------------------------------------------------------------
# kiutils loading
# ---------------------------------------------------------------------------


def load_board(path: str | Path, *, loader: Any | None = None) -> BoardModel:
    """Parse a ``.kicad_pcb`` file into a :class:`BoardModel`.

    Raises :class:`KiutilsUnavailableError` when ``kiutils`` is not installed and
    :class:`BoardParseError` when the file is missing or unreadable.
    """
    board_path = Path(path)
    if not board_path.is_file():
        raise BoardParseError(f"board not found: {board_path}")

    board_type = loader if loader is not None else _load_board_type()
    try:
        board = board_type.from_file(str(board_path))
    except Exception as exc:  # kiutils raises assorted parser errors
        raise BoardParseError(f"failed to parse {board_path}: {exc}") from exc
    return _board_to_model(board, board_path)


def _load_board_type() -> Any:
    try:
        module = importlib.import_module("kiutils.board")
    except ImportError as exc:  # pragma: no cover - exercised via injected loader in tests
        raise KiutilsUnavailableError(
            "kiutils is not installed; install atomc-plugin-atopile[pcb] to parse .kicad_pcb files"
        ) from exc
    return module.Board


def _board_to_model(board: Any, path: Path) -> BoardModel:
    thickness = _get_float(getattr(getattr(board, "general", None), "thickness", None), 1.6)
    layers = _copper_layer_count(board)
    footprints = tuple(
        fp for fp in (_footprint_model(raw) for raw in getattr(board, "footprints", []) or [])
    )
    nets: dict[str, str] = {}
    for fp in footprints:
        for pad in fp.pads:
            nid = net_id(pad.net_name or "")
            if nid is not None and pad.net_name is not None:
                nets[nid] = pad.net_name
    outline = _outline(board, footprints)
    return BoardModel(
        path=str(path),
        thickness_mm=thickness,
        layers=layers,
        outline=outline,
        footprints=footprints,
        nets=nets,
    )


def _footprint_model(raw: Any) -> FootprintModel:
    properties = getattr(raw, "properties", {}) or {}
    if not isinstance(properties, Mapping):
        properties = {}
    reference = properties.get("Reference")
    value = properties.get("Value")
    mpn = properties.get("MPN") or properties.get("Partnumber") or properties.get("mpn")
    position = getattr(raw, "position", None)
    x = _get_float(getattr(position, "X", None), 0.0)
    y = _get_float(getattr(position, "Y", None), 0.0)
    angle = _get_float(getattr(position, "angle", None), 0.0)
    layer = str(getattr(raw, "layer", "") or "")
    side = "bottom" if layer.startswith("B.") else "top"
    pads = tuple(_pad_model(raw, pad) for pad in getattr(raw, "pads", []) or [])
    return FootprintModel(
        reference=str(reference) if reference else None,
        lib_id=str(getattr(raw, "libId", "") or ""),
        value=str(value) if value else None,
        mpn=str(mpn) if mpn else None,
        x=x,
        y=y,
        rotation_deg=angle,
        side=side,
        pads=pads,
    )


def _pad_model(footprint: Any, pad: Any) -> PadModel:
    position = getattr(pad, "position", None)
    local_x = _get_float(getattr(position, "X", None), 0.0)
    local_y = _get_float(getattr(position, "Y", None), 0.0)
    fp_position = getattr(footprint, "position", None)
    fp_x = _get_float(getattr(fp_position, "X", None), 0.0)
    fp_y = _get_float(getattr(fp_position, "Y", None), 0.0)
    angle = math.radians(_get_float(getattr(fp_position, "angle", None), 0.0))
    rotated_x = local_x * math.cos(angle) - local_y * math.sin(angle)
    rotated_y = local_x * math.sin(angle) + local_y * math.cos(angle)
    pad_net = getattr(pad, "net", None)
    net_name = getattr(pad_net, "name", None) if pad_net is not None else None
    return PadModel(
        number=str(getattr(pad, "number", "") or ""),
        net_name=str(net_name) if net_name else None,
        x=fp_x + rotated_x,
        y=fp_y + rotated_y,
    )


def _copper_layer_count(board: Any) -> int:
    count = 0
    for layer in getattr(board, "layers", []) or []:
        name = getattr(layer, "name", None) or getattr(layer, "userName", None) or ""
        if str(name).endswith(".Cu"):
            count += 1
    return count or 2


def _get_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except TypeError, ValueError:
        return default


# ---------------------------------------------------------------------------
# Outline extraction
# ---------------------------------------------------------------------------


def _outline(
    board: Any,
    footprints: Sequence[FootprintModel],
) -> tuple[tuple[float, float], ...]:
    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for item in getattr(board, "graphicItems", []) or []:
        layer = getattr(item, "layer", None)
        if str(layer) != "Edge.Cuts":
            continue
        start = _point(getattr(item, "start", None))
        end = _point(getattr(item, "end", None))
        middle = _point(getattr(item, "mid", None))
        if start is not None and end is not None:
            segments.append((start, end))
        if start is not None and middle is not None:
            segments.append((start, middle))
        if middle is not None and end is not None:
            segments.append((middle, end))
    chained = _chain(segments)
    if len(chained) >= 3:
        return chained
    return _bbox_outline(footprints)


def _point(node: Any) -> tuple[float, float] | None:
    if node is None:
        return None
    x = getattr(node, "X", None)
    y = getattr(node, "Y", None)
    if x is None or y is None:
        return None
    return (round(float(x), 6), round(float(y), 6))


def _chain(
    segments: Sequence[tuple[tuple[float, float], tuple[float, float]]],
) -> tuple[tuple[float, float], ...]:
    if not segments:
        return ()
    remaining = list(segments)
    first_start, first_end = remaining.pop(0)
    chain = [first_start, first_end]
    while remaining:
        last = chain[-1]
        for index, (a, b) in enumerate(remaining):
            if a == last:
                chain.append(b)
                remaining.pop(index)
                break
            if b == last:
                chain.append(a)
                remaining.pop(index)
                break
        else:
            return ()
    if len(chain) >= 4 and chain[0] == chain[-1]:
        return tuple(chain[:-1])
    return ()


def _bbox_outline(footprints: Sequence[FootprintModel]) -> tuple[tuple[float, float], ...]:
    points = [(pad.x, pad.y) for fp in footprints for pad in fp.pads]
    if not points:
        return ()
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    margin = 5.0
    min_x, max_x = min(xs) - margin, max(xs) + margin
    min_y, max_y = min(ys) - margin, max(ys) + margin
    if min_x == max_x or min_y == max_y:
        return ()
    return (
        (min_x, min_y),
        (max_x, min_y),
        (max_x, max_y),
        (min_x, max_y),
    )


# ---------------------------------------------------------------------------
# IR mapping
# ---------------------------------------------------------------------------


def board_to_electrical(board: BoardModel) -> dict[str, Any]:
    """Map board footprints/pads to ``components`` and ``nets`` IR dictionaries."""
    components: list[dict[str, Any]] = []
    nets: dict[str, str] = {}
    for footprint in board.footprints:
        if not footprint.reference:
            continue
        pins: list[dict[str, Any]] = []
        for pad in footprint.pads:
            nid = net_id(pad.net_name or "")
            pin: dict[str, Any] = {"number": pad.number}
            if nid is not None and pad.net_name is not None:
                pin["net_ref"] = nid
                nets[nid] = pad.net_name
            pins.append(pin)
        components.append(
            {
                "id": f"comp:{footprint.reference}",
                "designator": footprint.reference,
                "mpn": footprint.mpn,
                "value": footprint.value,
                "package": footprint.lib_id or None,
                "dnp": False,
                "attributes": {},
                "pins": pins,
            }
        )
    return {
        "components": components,
        "nets": [{"id": nid, "name": name} for nid, name in nets.items()],
    }


def board_to_layout(
    board: BoardModel,
    *,
    valid_component_ids: Iterable[str],
    valid_net_ids: Iterable[str],
    existing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the ``/layout`` node fields from a parsed board.

    List-valued fields are merged with ``existing`` so that references the parser cannot
    reproduce (for example hand-authored test pads) survive an import. New placements and test
    pads are dropped when their ``component_ref``/``net_ref`` would dangle, keeping the document
    referentially valid.
    """
    current = existing or {}
    component_ids = set(valid_component_ids)
    net_ids = set(valid_net_ids)

    if not board.outline:
        raise BoardParseError(
            f"{board.path} has no Edge.Cuts geometry and no footprint pads to bound an outline"
        )

    placements: dict[str, dict[str, Any]] = {
        str(item["component_ref"]): dict(item)
        for item in current.get("placements") or []
        if isinstance(item, Mapping) and item.get("component_ref")
    }
    for footprint in board.footprints:
        if not footprint.reference:
            continue
        component_id = f"comp:{footprint.reference}"
        if component_id not in component_ids:
            continue
        placements[component_id] = {
            "component_ref": component_id,
            "x": footprint.x,
            "y": footprint.y,
            "rotation_deg": footprint.rotation_deg,
            "side": footprint.side,
        }

    test_pads: dict[str, dict[str, Any]] = {
        str(item["id"]): dict(item)
        for item in current.get("test_pads") or []
        if isinstance(item, Mapping) and item.get("id")
    }
    for footprint in board.footprints:
        if not footprint.reference or not _is_test_point(footprint):
            continue
        net_ref = _first_net_ref(footprint)
        if net_ref is None or net_ref not in net_ids:
            continue
        test_pads[f"pad:{footprint.reference}"] = {
            "id": f"pad:{footprint.reference}",
            "net_ref": net_ref,
            "x": footprint.x,
            "y": footprint.y,
            "side": footprint.side,
            "kind": "pogo",
            "label": _first_net_name(footprint),
        }

    return {
        "source": {"kind": "kicad_pcb", "path": board.path},
        "layers": board.layers,
        "outline": {
            "polygon": [list(point) for point in board.outline],
            "thickness_mm": board.thickness_mm,
        },
        "placements": list(placements.values()),
        "test_pads": list(test_pads.values()),
    }


def _is_test_point(footprint: FootprintModel) -> bool:
    reference = footprint.reference or ""
    return reference.startswith("TP") or "TestPoint" in footprint.lib_id


def _first_net_ref(footprint: FootprintModel) -> str | None:
    for pad in footprint.pads:
        nid = net_id(pad.net_name or "")
        if nid is not None:
            return nid
    return None


def _first_net_name(footprint: FootprintModel) -> str | None:
    for pad in footprint.pads:
        if pad.net_name:
            return pad.net_name
    return None
