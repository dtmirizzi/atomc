"""atomc cad-jig plugin.

Derives parametric switch-plate, tray-case and pogo-jig model data from the system IR, exposes
five mechanical gates and the ``cad.generate`` tool. Importing this package never imports
build123d; that only happens inside ``cad.generate`` when the toolchain is available.
"""

from __future__ import annotations

from .plugin import MANIFEST, PLUGIN_VERSION, PRODUCED_BY, CadJigPlugin, plugin

__all__ = [
    "MANIFEST",
    "PLUGIN_VERSION",
    "PRODUCED_BY",
    "CadJigPlugin",
    "plugin",
]
