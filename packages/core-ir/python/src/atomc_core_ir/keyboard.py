"""``keyboard`` domain node — matrix, keys, USB ids and QMK metadata."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .common import AtomcModel, IrId, NodeMeta


class Matrix(AtomcModel):
    rows: int = Field(ge=1)
    cols: int = Field(ge=1)
    diode_direction: Literal["COL2ROW", "ROW2COL"]
    row_pins: list[str] = Field(default_factory=list)
    col_pins: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_pin_counts(self) -> Matrix:
        if len(self.row_pins) != self.rows:
            raise ValueError(f"row_pins has {len(self.row_pins)} entries but rows={self.rows}")
        if len(self.col_pins) != self.cols:
            raise ValueError(f"col_pins has {len(self.col_pins)} entries but cols={self.cols}")
        return self


class Key(AtomcModel):
    id: IrId
    row: int = Field(ge=0)
    col: int = Field(ge=0)
    x_u: float = 0.0
    y_u: float = 0.0
    w_u: float = 1.0
    h_u: float = 1.0
    rotation_deg: float = 0.0
    switch_ref: IrId | None = None
    diode_ref: IrId | None = None
    label: str | None = None
    keycode_default: str | None = None


class Usb(AtomcModel):
    vid: str
    pid: str
    manufacturer: str
    product: str
    device_version: str = "1.0.0"


class Qmk(AtomcModel):
    keyboard_path: str
    bootloader: str = "stm32-dfu"
    processor: str = "STM32F411"
    board: str | None = None


class Keyboard(AtomcModel):
    meta_: NodeMeta = Field(alias="_meta")
    matrix: Matrix
    keys: list[Key] = Field(default_factory=list)
    usb: Usb
    qmk: Qmk

    @model_validator(mode="after")
    def _check_keys(self) -> Keyboard:
        seen: dict[tuple[int, int], str] = {}
        for key in self.keys:
            if key.row >= self.matrix.rows:
                raise ValueError(
                    f"key {key.id} row {key.row} out of range 0..{self.matrix.rows - 1}"
                )
            if key.col >= self.matrix.cols:
                raise ValueError(
                    f"key {key.id} col {key.col} out of range 0..{self.matrix.cols - 1}"
                )
            pos = (key.row, key.col)
            if pos in seen:
                raise ValueError(f"duplicate key position {pos} used by {seen[pos]} and {key.id}")
            seen[pos] = key.id
        return self
