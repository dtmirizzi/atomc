"""Top-level ``SystemIR`` document model plus load/dump and referential integrity."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

from pydantic import Field, model_validator

from .common import AtomcModel, IrId, JSONValue, NodeMeta, Timestamp
from .electrical import Electrical
from .fabrication import Fabrication
from .firmware import Firmware
from .gates import Gates
from .keyboard import Keyboard
from .layout import Layout
from .mechanical import Mechanical
from .orders import Orders
from .provenance import Provenance
from .simulation import Simulation
from .sourcing import Sourcing

SCHEMA_VERSION = "0.1.0"


class RefIntegrityError(ValueError):
    """Raised when an id is duplicated or a ``*_ref`` does not resolve."""


class DocumentMeta(AtomcModel):
    project_id: IrId
    name: str
    description: str | None = None
    created_at: Timestamp
    modified_at: Timestamp
    rev: int = Field(default=0, ge=0)
    atomc_version: str


class SystemIR(AtomcModel):
    """The unified system IR document (``system_ir.json``)."""

    schema_version: str = SCHEMA_VERSION
    meta: DocumentMeta
    electrical: Electrical | None = None
    layout: Layout | None = None
    keyboard: Keyboard | None = None
    firmware: Firmware | None = None
    simulation: Simulation | None = None
    mechanical: Mechanical | None = None
    sourcing: Sourcing | None = None
    fabrication: Fabrication | None = None
    orders: Orders | None = None
    gates: Gates | None = None
    provenance: Provenance | None = None
    ext: dict[str, dict[str, JSONValue]] = Field(default_factory=dict)

    DOMAIN_NODES: ClassVar[tuple[str, ...]] = (
        "electrical",
        "layout",
        "keyboard",
        "firmware",
        "simulation",
        "mechanical",
        "sourcing",
        "fabrication",
        "orders",
        "gates",
        "provenance",
    )

    @model_validator(mode="after")
    def _check_schema_version(self) -> SystemIR:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported schema_version {self.schema_version!r}; expected {SCHEMA_VERSION!r}"
            )
        return self

    # -- constructors -------------------------------------------------------

    @classmethod
    def empty(cls, project_id: str, name: str) -> SystemIR:
        """Create a minimal document (``meta`` only), at document rev 0."""
        now = _now()
        return cls(
            meta=DocumentMeta(
                project_id=project_id,
                name=name,
                created_at=now,
                modified_at=now,
                rev=0,
                atomc_version=SCHEMA_VERSION,
            )
        )

    @classmethod
    def load(cls, source: str | Path | bytes) -> SystemIR:
        """Load and validate a document from a path, path-like string, JSON text or bytes.

        A ``str`` that exists on disk is treated as a path; otherwise it is parsed as JSON
        text. Referential integrity is checked after schema validation.
        """
        text = _read_source(source)
        ir = cls.model_validate_json(text)
        ir.validate_refs()
        return ir

    # -- serialisation ------------------------------------------------------

    def dump(self) -> str:
        """Canonical JSON: sorted keys, 2-space indent, ``null`` optionals omitted, newline."""
        payload = self.model_dump(mode="json", by_alias=True, exclude_none=True)
        return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"

    # -- referential integrity ---------------------------------------------

    def validate_refs(self) -> None:
        """Ensure all ids are unique document-wide and every ``*_ref`` resolves."""
        ids = self._collect_ids()
        for ref, location in self._collect_refs():
            if ref not in ids:
                raise RefIntegrityError(
                    f"dangling reference {ref!r} at {location}: no such id in document"
                )

    def _collect_ids(self) -> dict[str, str]:
        seen: dict[str, str] = {}

        def add(value: str, location: str) -> None:
            if value in seen:
                raise RefIntegrityError(
                    f"duplicate id {value!r} at {location} (already defined at {seen[value]})"
                )
            seen[value] = location

        if self.electrical is not None:
            elec = self.electrical
            for i, comp in enumerate(elec.components):
                add(comp.id, f"/electrical/components/{i}")
            for i, net in enumerate(elec.nets):
                add(net.id, f"/electrical/nets/{i}")
            for i, assertn in enumerate(elec.assertions):
                add(assertn.id, f"/electrical/assertions/{i}")
            for i, ercv in enumerate(elec.erc):
                add(ercv.id, f"/electrical/erc/{i}")
        if self.layout is not None:
            lay = self.layout
            for i, tpad in enumerate(lay.test_pads):
                add(tpad.id, f"/layout/test_pads/{i}")
            for i, hole in enumerate(lay.mounting_holes):
                add(hole.id, f"/layout/mounting_holes/{i}")
            for i, kout in enumerate(lay.keepouts):
                add(kout.id, f"/layout/keepouts/{i}")
        if self.keyboard is not None:
            for i, key in enumerate(self.keyboard.keys):
                add(key.id, f"/keyboard/keys/{i}")
        if self.firmware is not None:
            fw = self.firmware
            for i, target in enumerate(fw.targets):
                add(target.id, f"/firmware/targets/{i}")
                for j, art in enumerate(target.artifacts):
                    add(art.id, f"/firmware/targets/{i}/artifacts/{j}")
            for i, periph in enumerate(fw.peripherals):
                add(periph.id, f"/firmware/peripherals/{i}")
            for i, suite in enumerate(fw.suites):
                add(suite.id, f"/firmware/suites/{i}")
        if self.simulation is not None:
            sim = self.simulation
            for i, scen in enumerate(sim.scenarios):
                add(scen.id, f"/simulation/scenarios/{i}")
            for i, cap in enumerate(sim.captures):
                add(cap.id, f"/simulation/captures/{i}")
        if self.mechanical is not None:
            mech = self.mechanical
            for i, mart in enumerate(mech.artifacts):
                add(mart.id, f"/mechanical/artifacts/{i}")
            for i, check in enumerate(mech.checks):
                add(check.id, f"/mechanical/checks/{i}")
        if self.sourcing is not None:
            for i, line in enumerate(self.sourcing.bom):
                add(line.id, f"/sourcing/bom/{i}")
                for j, offer in enumerate(line.offers):
                    add(offer.id, f"/sourcing/bom/{i}/offers/{j}")
        if self.fabrication is not None:
            for i, q in enumerate(self.fabrication.quotes):
                add(q.id, f"/fabrication/quotes/{i}")
        if self.orders is not None:
            for i, o in enumerate(self.orders.orders):
                add(o.id, f"/orders/orders/{i}")
        if self.gates is not None:
            for gate_key, result in self.gates.results.items():
                add(result.id, f"/gates/results/{gate_key}")
        return seen

    def _collect_refs(self) -> list[tuple[str, str]]:
        refs: list[tuple[str, str]] = []

        def add(value: str | None, location: str) -> None:
            if value is not None:
                refs.append((value, location))

        def add_many(values: list[str], location: str) -> None:
            for i, value in enumerate(values):
                refs.append((value, f"{location}/{i}"))

        if self.electrical is not None:
            for i, comp in enumerate(self.electrical.components):
                for j, pin in enumerate(comp.pins):
                    add(pin.net_ref, f"/electrical/components/{i}/pins/{j}/net_ref")
            for i, e in enumerate(self.electrical.erc):
                add_many(e.refs, f"/electrical/erc/{i}/refs")
        if self.layout is not None:
            for i, p in enumerate(self.layout.placements):
                add(p.component_ref, f"/layout/placements/{i}/component_ref")
            for i, t in enumerate(self.layout.test_pads):
                add(t.net_ref, f"/layout/test_pads/{i}/net_ref")
        if self.keyboard is not None:
            for i, k in enumerate(self.keyboard.keys):
                add(k.switch_ref, f"/keyboard/keys/{i}/switch_ref")
                add(k.diode_ref, f"/keyboard/keys/{i}/diode_ref")
        if self.firmware is not None:
            for i, periph in enumerate(self.firmware.peripherals):
                for j, sig in enumerate(periph.signals):
                    add(sig.net_ref, f"/firmware/peripherals/{i}/signals/{j}/net_ref")
        if self.simulation is not None:
            for i, cap in enumerate(self.simulation.captures):
                add(cap.scenario_ref, f"/simulation/captures/{i}/scenario_ref")
        if self.mechanical is not None:
            for i, b in enumerate(self.mechanical.component_bboxes):
                add(b.component_ref, f"/mechanical/component_bboxes/{i}/component_ref")
        if self.sourcing is not None:
            for i, line in enumerate(self.sourcing.bom):
                add_many(line.component_refs, f"/sourcing/bom/{i}/component_refs")
                add(line.chosen_offer_ref, f"/sourcing/bom/{i}/chosen_offer_ref")
        if self.gates is not None:
            for key, result in self.gates.results.items():
                add_many(result.refs, f"/gates/results/{key}/refs")
                for i, ev in enumerate(result.evidence):
                    add(ev.ref, f"/gates/results/{key}/evidence/{i}/ref")
        return refs


def _read_source(source: str | Path | bytes) -> str:
    if isinstance(source, bytes):
        return source.decode("utf-8")
    if isinstance(source, Path):
        return source.read_text(encoding="utf-8")
    path = Path(source)
    try:
        if path.exists() and path.is_file():
            return path.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover - very long strings are not paths
        pass
    return source


def _now() -> Any:
    from datetime import UTC, datetime

    return datetime.now(UTC)


def export_json_schema() -> dict[str, Any]:
    """Return the JSON Schema for ``SystemIR`` (datetimes as RFC 3339 strings)."""
    return SystemIR.model_json_schema(by_alias=True)


def make_node_meta(rev: int = 0) -> NodeMeta:
    """Helper for tests/plugins building a new top-level node."""
    return NodeMeta(rev=rev, lock=None)
