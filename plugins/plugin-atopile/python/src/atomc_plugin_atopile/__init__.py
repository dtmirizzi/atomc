"""``atomc_plugin_atopile`` — the built-in atopile plugin.

Public surface: the decorated :data:`plugin` instance the daemon loads from the
``atomc.plugins`` entry point, plus the :class:`AtopilePlugin` class for tests.
"""

from __future__ import annotations

from .plugin import AtopilePlugin, plugin

__all__ = ["AtopilePlugin", "plugin"]
