"""atomc QMK plugin package."""

from __future__ import annotations

from .manifest import MANIFEST, PLUGIN_NAME, PLUGIN_VERSION
from .plugin import QmkPlugin, plugin

__all__ = ["MANIFEST", "PLUGIN_NAME", "PLUGIN_VERSION", "QmkPlugin", "plugin"]
