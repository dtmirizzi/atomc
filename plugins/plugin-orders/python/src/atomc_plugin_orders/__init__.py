"""atomc orders plugin.

Turns chosen ``/sourcing`` offers into per-vendor cart files, records DRAFT-only ``/orders``
entries for a human to place, and applies deterministic mock-carrier tracking. No tool in this
package ever contacts a vendor or places a real order.
"""

from __future__ import annotations

from .manifest import PLUGIN_NAME, PLUGIN_VERSION
from .plugin import DRAFT_NOTICE, OrdersPlugin, plugin

__all__ = ["DRAFT_NOTICE", "PLUGIN_NAME", "PLUGIN_VERSION", "OrdersPlugin", "plugin"]
