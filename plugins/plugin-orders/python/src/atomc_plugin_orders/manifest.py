"""The shared ``atomc-plugin.json`` manifest and its SDK representation.

The manifest document is the single source of truth at ``plugins/plugin-orders/atomc-plugin.json``
(copied next to this module inside a wheel). Two established integration quirks apply:

* The Python SDK's ``conformance()`` re-validates a parsed manifest by dumping it back to JSON;
  a Python-only runtime dump includes ``"ts": null``, which the shared schema rejects.
  :class:`ConformantManifest` drops ``None`` fields on dump so re-validation round-trips.
* The daemon's entry-point resolver validates the object's ``.manifest`` into its own model, so
  the runtime instance exposes the raw dict rather than relying on ``__atomc_manifest__``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from atomc_plugin_sdk import PluginManifest, load_manifest

__all__ = [
    "MANIFEST_FILENAME",
    "PLUGIN_NAME",
    "PLUGIN_VERSION",
    "ConformantManifest",
    "conformant_manifest",
    "load_plugin_manifest",
    "manifest_dict",
    "manifest_path",
]

MANIFEST_FILENAME = "atomc-plugin.json"
PLUGIN_NAME = "orders"
PLUGIN_VERSION = "0.1.0"


class ConformantManifest(PluginManifest):
    """A :class:`PluginManifest` whose JSON dump omits absent optional fields."""

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)


def manifest_path() -> Path:
    """Return the first ``atomc-plugin.json`` beside the package or in a parent directory."""
    here = Path(__file__).resolve()
    candidates = [here.parent / MANIFEST_FILENAME]
    candidates.extend(parent / MANIFEST_FILENAME for parent in here.parents)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"could not locate {MANIFEST_FILENAME} next to {here} or any parent directory"
    )


@lru_cache(maxsize=1)
def load_plugin_manifest() -> PluginManifest:
    """Load and validate the shared manifest (cached for the process)."""
    return load_manifest(manifest_path())


@lru_cache(maxsize=1)
def manifest_dict() -> dict[str, Any]:
    """Return the raw manifest document as a plain dict."""
    data = json.loads(manifest_path().read_text(encoding="utf-8"))
    if not isinstance(data, dict):  # pragma: no cover - guarded by validate_manifest
        raise TypeError("atomc-plugin.json must contain a JSON object")
    return data


@lru_cache(maxsize=1)
def conformant_manifest() -> ConformantManifest:
    """Return the validated manifest as a :class:`ConformantManifest` for SDK conformance."""
    return ConformantManifest.model_validate(manifest_dict())
