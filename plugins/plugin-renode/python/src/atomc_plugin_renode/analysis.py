"""Pure analysis of captured Renode output.

Kept separate from the plugin so the PASS/FAIL/SKIP rules are unit-testable without a subprocess
and without Renode. The rules are deliberately conservative: a run only ``PASS``es when a
configured boot banner is observed *and* no fault is; anything else is ``FAIL`` with evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .runner import RenodeRunResult

__all__ = [
    "MAX_EVIDENCE_CHARS",
    "BootVerdict",
    "classify_boot",
    "tail",
]

MAX_EVIDENCE_CHARS = 6000
"""Evidence logs are truncated to this many trailing characters."""

FAULT_MARKERS = ("hardfault", "hard fault", "hard-fault")
"""Case-insensitive substrings that indicate a Cortex-M fault."""

BootStatus = Literal["PASS", "FAIL"]


@dataclass(frozen=True, slots=True)
class BootVerdict:
    """The classification of one emulation run."""

    status: BootStatus
    summary: str
    fault: bool = False


def tail(text: str, limit: int = MAX_EVIDENCE_CHARS) -> str:
    """Return the trailing ``limit`` characters of ``text`` (bounded evidence)."""
    if limit <= 0:
        return ""
    return text if len(text) <= limit else text[-limit:]


def classify_boot(result: RenodeRunResult, markers: tuple[str, ...]) -> BootVerdict:
    """Classify a run as PASS or FAIL from its output and exit status.

    * A Cortex-M fault anywhere in the output is always ``FAIL``.
    * A configured banner makes the run ``PASS`` even if the process was killed at the timeout
      (Renode has no self-quit; the run window is enforced by the caller).
    * Otherwise a timeout, a non-zero exit, or a clean-but-bannerless run is ``FAIL``.
    """
    output = result.combined_output
    lowered = output.lower()
    if any(marker in lowered for marker in FAULT_MARKERS):
        return BootVerdict(status="FAIL", summary="HardFault observed in Renode output", fault=True)
    for marker in markers:
        if marker and marker in output:
            return BootVerdict(status="PASS", summary=f"boot banner {marker!r} observed")
    if result.timed_out:
        return BootVerdict(status="FAIL", summary="timeout before a boot banner was observed")
    if result.exit_code not in (0, None):
        return BootVerdict(status="FAIL", summary=f"renode exited with code {result.exit_code}")
    return BootVerdict(status="FAIL", summary="no boot banner observed in Renode output")
