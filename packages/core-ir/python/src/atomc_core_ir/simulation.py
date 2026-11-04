"""``simulation`` domain node — generated Renode artifacts, scenarios and captures."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import AtomcModel, IrId, NodeMeta


class Platform(AtomcModel):
    repl_path: str | None = None
    resc_path: str | None = None
    generated_from_rev: int | None = Field(default=None, ge=0)


class Fault(AtomcModel):
    kind: Literal["stuck_key", "ghost", "brownout", "sensor_nack", "custom"]
    params: dict[str, object] = Field(default_factory=dict)


class Scenario(AtomcModel):
    id: IrId
    description: str | None = None
    fault: Fault | None = None


class Capture(AtomcModel):
    id: IrId
    kind: Literal["uart", "gpio", "wavedrom", "hid"]
    path: str
    scenario_ref: IrId | None = None


class Simulation(AtomcModel):
    meta_: NodeMeta = Field(alias="_meta")
    platform: Platform
    scenarios: list[Scenario] = Field(default_factory=list)
    captures: list[Capture] = Field(default_factory=list)
