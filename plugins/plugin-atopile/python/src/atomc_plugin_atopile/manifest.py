"""The plugin's shared ``atomc-plugin.json`` manifest and its SDK representation.

Two integration gaps force a slightly unusual shape here, both outside this plugin's ownership:

* The Python SDK's ``conformance()`` re-validates a parsed manifest by dumping it back to JSON;
  with a Python-only ``runtime`` that dump includes ``"ts": null``, which the shared manifest
  schema rejects. :class:`ConformantManifest` drops ``None`` fields on dump so re-validation
  round-trips.
* The daemon's entry-point resolver validates ``__atomc_manifest__`` straight into its own
  ``Manifest`` model, which rejects an SDK ``PluginManifest`` instance. The runtime object
  therefore exposes the raw manifest document as ``.manifest`` (a dict the daemon can validate)
  rather than decorating with ``__atomc_manifest__``.

Both are reported as root/integration changes in the WP-4.1 handoff.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from atomc_plugin_sdk import PluginManifest, load_manifest

__all__ = [
    "MANIFEST_FILENAME",
    "ConformantManifest",
    "conformant_manifest",
    "load_plugin_manifest",
    "manifest_dict",
    "manifest_path",
]

MANIFEST_FILENAME = "atomc-plugin.json"


class ConformantManifest(PluginManifest):
    """A :class:`PluginManifest` whose JSON dump omits absent optional fields."""

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)


def manifest_path() -> Path:
    """Return the first ``atomc-plugin.json`` found beside the package or in a parent directory.

    The monorepo keeps the manifest at the plugin root (shared by any TS runtime); a wheel ships
    a copy next to this module.
    """
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
