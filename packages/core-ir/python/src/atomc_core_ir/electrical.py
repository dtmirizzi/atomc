"""``electrical`` domain node — components, nets, assertions, ERC results."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import AtomcModel, IrId, NodeMeta, VoltageV


class ElectricalSource(AtomcModel):
    kind: Literal["atopile"]
    entry: str
    ato_version: str | None = None


class Pin(AtomcModel):
    number: str
    name: str | None = None
    net_ref: IrId | None = None


class Component(AtomcModel):
    id: IrId
    designator: str
    mpn: str | None = None
    manufacturer: str | None = None
    value: str | None = None
    description: str | None = None
    footprint: str | None = None
    lcsc: str | None = None
    package: str | None = None
    dnp: bool = False
    attributes: dict[str, str] = Field(default_factory=dict)
    pins: list[Pin] = Field(default_factory=list)


class Net(AtomcModel):
    id: IrId
    name: str
    net_class: Literal["power", "ground", "signal", "diff", "usb", "other"] | None = Field(
        default=None, alias="class"
    )
    voltage_v: VoltageV | None = None


class Assertion(AtomcModel):
    id: IrId
    expr: str
    status: Literal["pass", "fail", "unknown"] = "unknown"
    message: str | None = None


class ErcViolation(AtomcModel):
    id: IrId
    rule: str
    severity: Literal["error", "warning"]
    message: str
    refs: list[IrId] = Field(default_factory=list)


class Electrical(AtomcModel):
    meta_: NodeMeta = Field(alias="_meta")
    source: ElectricalSource
    components: list[Component] = Field(default_factory=list)
    nets: list[Net] = Field(default_factory=list)
    assertions: list[Assertion] = Field(default_factory=list)
    erc: list[ErcViolation] = Field(default_factory=list)
