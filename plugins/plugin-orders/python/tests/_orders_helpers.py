"""Shared fixtures: a fake plugin context and small IR builders.

The fake context mirrors the daemon's ``PluginContext`` and applies real RFC 6902 transactions
through ``atomc_core_ir.apply_patch``, so tests exercise the same write path the daemon uses.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from atomc_core_ir import SystemIR, TxResult, apply_patch

TS = "2026-11-04T00:00:00Z"


class FakeLogger:
    """No-op structured logger capturing records for assertions."""

    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict[str, Any]]] = []

    def _log(self, level: str, msg: str, **fields: Any) -> None:
        self.records.append((level, msg, fields))

    def debug(self, msg: str, /, **fields: Any) -> None:
        self._log("debug", msg, **fields)

    def info(self, msg: str, /, **fields: Any) -> None:
        self._log("info", msg, **fields)

    def warning(self, msg: str, /, **fields: Any) -> None:
        self._log("warning", msg, **fields)

    def error(self, msg: str, /, **fields: Any) -> None:
        self._log("error", msg, **fields)


class FakeContext:
    """An in-memory ``PluginContext`` backed by a real ``SystemIR``."""

    def __init__(self, ir: SystemIR, root: Path) -> None:
        self.ir = ir
        self.root = root
        self.logger = FakeLogger()
        self.transactions: list[tuple[str, int, list[dict[str, Any]]]] = []

    @property
    def artifact_root(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def _document(self) -> dict[str, Any]:
        return self.ir.model_dump(mode="json", by_alias=True)

    def _resolve(self, path: str) -> Any:
        if path in ("", "/"):
            return self._document()
        parts = path.strip("/").split("/")
        current: Any = self._document()
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list):
                current = current[int(part)]
            else:
                raise ValueError(f"pointer {path!r} not found")
        return current

    def _node_rev(self, path: str) -> int:
        name = path.strip("/").split("/")[0]
        node = self._document().get(name)
        if node is None:
            raise ValueError(f"node /{name} is not present")
        return int(node.get("_meta", {}).get("rev", 0))

    async def ir_get(self, path: str = "/") -> Any:
        return self._resolve(path)

    async def ir_read(self, path: str = "/") -> dict[str, Any]:
        return {"rev": self._node_rev(path), "value": self._resolve(path)}

    async def ir_transact(self, path: str, base_rev: int, ops: list[dict[str, Any]]) -> TxResult:
        self.ir, result = apply_patch(self.ir, path, base_rev, ops)
        self.transactions.append((path, base_rev, ops))
        return result


def build_ir(**nodes: Any) -> SystemIR:
    """Build a validated ``SystemIR`` from node dicts, adding ``_meta`` and document meta."""
    document: dict[str, Any] = {
        "meta": {
            "project_id": "proj:test",
            "name": "test",
            "created_at": TS,
            "modified_at": TS,
            "rev": 0,
            "atomc_version": "0.1.0",
        }
    }
    for name, value in nodes.items():
        if value is None:
            continue
        node = dict(value)
        node.setdefault("_meta", {"rev": 0})
        document[name] = node
    ir = SystemIR.model_validate(document)
    ir.validate_refs()
    return ir


def offer(
    *,
    offer_id: str,
    vendor: str,
    sku: str,
    stock: int = 100,
    moq: int = 1,
    price_breaks: list[dict[str, int]] | None = None,
) -> dict[str, Any]:
    """Shorthand for a frozen-IR ``Offer`` document."""
    return {
        "id": offer_id,
        "vendor": vendor,
        "sku": sku,
        "stock": stock,
        "moq": moq,
        "price_breaks": price_breaks or [{"qty": 1, "unit_price_minor": 10}],
        "currency": "USD",
        "fetched_at": TS,
    }


def bom_line(
    *,
    line_id: str,
    refs: list[str],
    offer_: dict[str, Any],
    qty_per_unit: int = 1,
    mpn: str | None = None,
    lcsc: str | None = None,
) -> dict[str, Any]:
    """Shorthand for a frozen-IR ``BomLine`` with one chosen offer."""
    line: dict[str, Any] = {
        "id": line_id,
        "component_refs": refs,
        "qty_per_unit": qty_per_unit,
        "offers": [offer_],
        "chosen_offer_ref": offer_["id"],
        "alternates": [],
    }
    if mpn is not None:
        line["mpn"] = mpn
    if lcsc is not None:
        line["lcsc"] = lcsc
    return line


def demo_ir(*, build_qty: int = 5) -> SystemIR:
    """A four-line BOM spanning lcsc, jlcpcb, mouser and digikey, plus matching components."""
    return build_ir(
        electrical={
            "source": {"kind": "atopile", "entry": "main.ato:App"},
            "components": [
                {
                    "id": "comp:U1",
                    "designator": "U1",
                    "mpn": "STM32F411CEU6",
                    "footprint": "QFN-48",
                    "pins": [],
                },
                {
                    "id": "comp:R1",
                    "designator": "R1",
                    "mpn": "RC0603FR-0710KL",
                    "footprint": "R_0603",
                    "pins": [],
                },
                {
                    "id": "comp:R2",
                    "designator": "R2",
                    "mpn": "CC0603KRX7R9BB104",
                    "footprint": "C_0603",
                    "pins": [],
                },
                {
                    "id": "comp:J1",
                    "designator": "J1",
                    "mpn": "USB4085-GF-A",
                    "footprint": "USB-C-16P",
                    "pins": [],
                },
            ],
            "nets": [],
            "assertions": [],
            "erc": [],
        },
        sourcing={
            "currency": "USD",
            "build_qty": build_qty,
            "budget": {"per_unit_minor": 1500, "total_minor": 7500},
            "bom": [
                bom_line(
                    line_id="bom:U1",
                    refs=["comp:U1"],
                    offer_=offer(
                        offer_id="offer:U1_lcsc",
                        vendor="lcsc",
                        sku="C60442",
                        price_breaks=[
                            {"qty": 1, "unit_price_minor": 420},
                            {"qty": 5, "unit_price_minor": 390},
                        ],
                    ),
                    mpn="STM32F411CEU6",
                    lcsc="C60442",
                ),
                bom_line(
                    line_id="bom:R1",
                    refs=["comp:R1"],
                    offer_=offer(
                        offer_id="offer:R1_mouser",
                        vendor="mouser",
                        sku="603-RC0603FR-0710KL",
                        price_breaks=[
                            {"qty": 1, "unit_price_minor": 2},
                            {"qty": 100, "unit_price_minor": 1},
                        ],
                    ),
                    qty_per_unit=2,
                    mpn="RC0603FR-0710KL",
                ),
                bom_line(
                    line_id="bom:R2",
                    refs=["comp:R2"],
                    offer_=offer(
                        offer_id="offer:R2_jlcpcb",
                        vendor="jlcpcb",
                        sku="C14663",
                    ),
                    qty_per_unit=4,
                    mpn="CC0603KRX7R9BB104",
                    lcsc="C14663",
                ),
                bom_line(
                    line_id="bom:J1",
                    refs=["comp:J1"],
                    offer_=offer(
                        offer_id="offer:J1_digikey",
                        vendor="digikey",
                        sku="1528-1234-ND",
                    ),
                    mpn="USB4085-GF-A",
                ),
            ],
        },
    )
