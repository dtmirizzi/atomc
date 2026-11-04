"""``firmware`` domain node — build targets, peripherals, test suites."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import (
    Artifact,
    AtomcModel,
    DurationMs,
    IrId,
    NodeMeta,
    Timestamp,
)


class MemoryRegion(AtomcModel):
    name: str
    origin: int = Field(ge=0)
    length: int = Field(gt=0)


class FwTarget(AtomcModel):
    id: IrId
    mcu: str
    core: str
    memory: list[MemoryRegion] = Field(default_factory=list)
    framework: Literal["qmk", "zephyr", "baremetal", "other"]
    source_dir: str
    build_cmd: str | None = None
    artifacts: list[Artifact] = Field(default_factory=list)


class Signal(AtomcModel):
    name: str
    pin: str
    net_ref: IrId | None = None


class PeriphMap(AtomcModel):
    id: IrId
    kind: Literal["uart", "gpio", "i2c", "spi", "usb", "can", "timer", "other"]
    base_address: int | None = Field(default=None, ge=0)
    signals: list[Signal] = Field(default_factory=list)


class TestRun(AtomcModel):
    ran_at: Timestamp
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    skipped: int = Field(ge=0)
    duration_ms: DurationMs = Field(ge=0)
    report_path: str | None = None


class TestSuite(AtomcModel):
    id: IrId
    path: str
    framework: Literal["pytest"] = "pytest"
    last_result: TestRun | None = None


class Firmware(AtomcModel):
    meta_: NodeMeta = Field(alias="_meta")
    targets: list[FwTarget] = Field(default_factory=list)
    peripherals: list[PeriphMap] = Field(default_factory=list)
    suites: list[TestSuite] = Field(default_factory=list)
