"""Exceptions raised by the orders plugin.

Everything the plugin raises subclasses :class:`PluginError` so a caller can distinguish a
plugin-level failure (bad request, illegal transition, missing data) from an unexpected crash.
"""

from __future__ import annotations

__all__ = [
    "CartBuildError",
    "IllegalTransitionError",
    "LedgerError",
    "PluginError",
]


class PluginError(Exception):
    """Base class for recoverable plugin failures."""


class CartBuildError(PluginError):
    """The /sourcing node could not be turned into a per-vendor cart."""


class LedgerError(PluginError):
    """The /orders ledger is missing, malformed or would be written illegally."""


class IllegalTransitionError(LedgerError):
    """An order status transition violates the draft→…→delivered state machine."""

    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(
            f"illegal order status transition {current!r} -> {target!r}; "
            "no order was modified and no vendor was contacted"
        )
