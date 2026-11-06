"""atomc sourcing plugin package.

Public entry point: ``atomc_plugin_sourcing:plugin`` (declared in ``atomc-plugin.json`` and the
``atomc.plugins`` entry-point group).
"""

from __future__ import annotations

from .manifest import MANIFEST_FILENAME, conformant_manifest, load_plugin_manifest, manifest_dict
from .plugin import SourcingPlugin, plugin

__all__ = [
    "MANIFEST_FILENAME",
    "SourcingPlugin",
    "conformant_manifest",
    "load_plugin_manifest",
    "manifest_dict",
    "plugin",
]
