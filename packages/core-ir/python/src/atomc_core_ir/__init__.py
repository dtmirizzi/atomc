"""``atomc_core_ir`` — Pydantic v2 models for the atomc unified system IR.

Public API per ``docs/architecture/contracts/ir-schema.md`` §5::

    SystemIR.load(source) -> SystemIR
    SystemIR.dump() -> str
    SystemIR.empty(project_id, name) -> SystemIR
    export_json_schema() -> dict
    apply_patch(ir, path, base_rev, ops, holder=None, now=None) -> (SystemIR, TxResult)
    acquire_lock(ir, node, holder, ttl_s, reason=None, now=None) -> SystemIR
    release_lock(ir, node, holder) -> SystemIR
    ConflictError, LockedError, RefIntegrityError
"""

from __future__ import annotations

from .common import (
    AngleDeg,
    Artifact,
    AtomcModel,
    CurrentMa,
    DurationDays,
    DurationMs,
    DurationS,
    DurationUs,
    IrId,
    JSONValue,
    LengthMm,
    Lock,
    MoneyMinor,
    NodeMeta,
    Point2,
    Point3,
    Polygon,
    Sha256,
    TemperatureC,
    Timestamp,
    VoltageV,
)
from .document import (
    SCHEMA_VERSION,
    DocumentMeta,
    RefIntegrityError,
    SystemIR,
    export_json_schema,
    make_node_meta,
)
from .electrical import Assertion, Component, Electrical, ElectricalSource, ErcViolation, Net, Pin
from .fabrication import Assembly, FabQuote, Fabrication, PcbSpec
from .firmware import Firmware, FwTarget, MemoryRegion, PeriphMap, Signal, TestRun, TestSuite
from .gates import Evidence, GateResult, Gates, Suggestion, SuggestionPatch
from .keyboard import Key, Keyboard, Matrix, Qmk, Usb
from .layout import Hole, Keepout, Layout, LayoutSource, Outline, Placement, TestPad
from .mechanical import BBox, ComponentBBox, Enclosure, Jig, Mechanical, MechCheck, Plate
from .orders import HistoryEntry, Order, OrderLine, Orders, Tracking
from .provenance import Provenance, ProvNode
from .simulation import Capture, Fault, Platform, Scenario, Simulation
from .sourcing import Alternate, BomLine, Budget, Offer, PriceBreak, Sourcing
from .tx import (
    ConflictError,
    LockedError,
    PatchError,
    TxResult,
    acquire_lock,
    apply_patch,
    release_lock,
)

__all__ = [
    # document
    "SCHEMA_VERSION",
    # sourcing
    "Alternate",
    # common
    "AngleDeg",
    "Artifact",
    # fabrication
    "Assembly",
    # electrical
    "Assertion",
    "AtomcModel",
    # mechanical
    "BBox",
    "BomLine",
    "Budget",
    # simulation
    "Capture",
    "Component",
    "ComponentBBox",
    # tx
    "ConflictError",
    "CurrentMa",
    "DocumentMeta",
    "DurationDays",
    "DurationMs",
    "DurationS",
    "DurationUs",
    "Electrical",
    "ElectricalSource",
    "Enclosure",
    "ErcViolation",
    # gates
    "Evidence",
    "FabQuote",
    "Fabrication",
    "Fault",
    # firmware
    "Firmware",
    "FwTarget",
    "GateResult",
    "Gates",
    # orders
    "HistoryEntry",
    # layout
    "Hole",
    "IrId",
    "JSONValue",
    "Jig",
    "Keepout",
    # keyboard
    "Key",
    "Keyboard",
    "Layout",
    "LayoutSource",
    "LengthMm",
    "Lock",
    "LockedError",
    "Matrix",
    "MechCheck",
    "Mechanical",
    "MemoryRegion",
    "MoneyMinor",
    "Net",
    "NodeMeta",
    "Offer",
    "Order",
    "OrderLine",
    "Orders",
    "Outline",
    "PatchError",
    "PcbSpec",
    "PeriphMap",
    "Pin",
    "Placement",
    "Plate",
    "Platform",
    "Point2",
    "Point3",
    "Polygon",
    "PriceBreak",
    "ProvNode",
    # provenance
    "Provenance",
    "Qmk",
    "RefIntegrityError",
    "Scenario",
    "Sha256",
    "Signal",
    "Simulation",
    "Sourcing",
    "Suggestion",
    "SuggestionPatch",
    "SystemIR",
    "TemperatureC",
    "TestPad",
    "TestRun",
    "TestSuite",
    "Timestamp",
    "Tracking",
    "TxResult",
    "Usb",
    "VoltageV",
    "acquire_lock",
    "apply_patch",
    # schema
    "export_json_schema",
    "make_node_meta",
    "release_lock",
]
