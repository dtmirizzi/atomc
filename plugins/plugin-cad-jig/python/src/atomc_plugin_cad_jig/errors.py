"""Errors raised while deriving parametric models from the system IR."""

from __future__ import annotations


class ModelDerivationError(ValueError):
    """The IR lacks or contradicts the data needed to derive a mechanical model.

    Carries the JSON-pointer-ish ``field`` that is missing or invalid so gate results and the
    tool can report actionable evidence rather than an opaque traceback.
    """

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        super().__init__(f"{field}: {message}")
