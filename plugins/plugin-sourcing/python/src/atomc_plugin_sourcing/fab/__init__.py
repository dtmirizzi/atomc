"""PCB fabrication quoting: vendor adapters, spec derivation, tools and the fab gate.

This package extends ``plugin-sourcing`` with a JLCPCB fabrication-quote adapter. Nothing here
invents prices: every :class:`~atomc_core_ir.FabQuote` traces to a parsed vendor response (or a
deterministic synthetic cassette in tests). With no credentials a live quote fails closed as
``UNAVAILABLE``.
"""

from __future__ import annotations

from .base import FabAdapter
from .jlcpcb import JlcpcbAdapter
from .service import FabReport, FabService, build_fab_adapters
from .spec import (
    DEFAULT_FAB_BUDGET_MINOR,
    DEFAULT_PCB_SPEC,
    budget_for_ir,
    pcb_spec_for_ir,
)

__all__ = [
    "DEFAULT_FAB_BUDGET_MINOR",
    "DEFAULT_PCB_SPEC",
    "FabAdapter",
    "FabReport",
    "FabService",
    "JlcpcbAdapter",
    "budget_for_ir",
    "build_fab_adapters",
    "pcb_spec_for_ir",
]
