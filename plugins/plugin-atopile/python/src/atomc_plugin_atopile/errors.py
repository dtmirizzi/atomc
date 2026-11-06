"""Exceptions raised by the atopile plugin.

Everything the plugin raises subclasses :class:`PluginError` so the daemon can distinguish a
plugin-level failure (bad request, missing toolchain) from an unexpected crash.
"""

from __future__ import annotations

__all__ = [
    "BoardParseError",
    "KiutilsUnavailableError",
    "PluginError",
]


class PluginError(Exception):
    """Base class for recoverable plugin failures."""


class KiutilsUnavailableError(PluginError):
    """``kiutils`` is not importable, so ``.kicad_pcb`` parsing cannot run."""


class BoardParseError(PluginError):
    """A ``.kicad_pcb`` file could not be parsed or produced no usable geometry."""
