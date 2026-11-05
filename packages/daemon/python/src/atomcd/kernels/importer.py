"""Lazy import helpers shared by the kernel adapters.

Import-safety rule for the whole package: nothing here imports a hardware engine. Adapters call
:func:`import_module` from inside ``_start`` so a bare ``import atomcd.kernels`` stays cheap and
side-effect free.
"""

from __future__ import annotations

import importlib
import importlib.util
from importlib.metadata import PackageNotFoundError, version
from types import ModuleType

from atomcd.kernels.health import ProbeResult


def module_available(name: str) -> bool:
    """Return whether ``name`` is importable, without importing it."""
    try:
        return importlib.util.find_spec(name) is not None
    except ImportError, ModuleNotFoundError, ValueError:
        return False


def module_version(distribution: str) -> str | None:
    """Return the installed distribution version, or ``None`` when absent."""
    try:
        return version(distribution)
    except PackageNotFoundError:
        return None


def import_module(name: str) -> ModuleType:
    """Import and return ``name`` (raises ``ImportError`` when missing)."""
    return importlib.import_module(name)


def probe_modules(*packages: str, distribution: str | None = None) -> ProbeResult:
    """Probe a set of module names and report availability plus version.

    ``distribution`` may name the PyPI distribution when it differs from the import name
    (for example module ``cv2`` → distribution ``opencv-python``).
    """
    missing = [pkg for pkg in packages if not module_available(pkg)]
    if missing:
        return ProbeResult(available=False, detail=f"missing: {', '.join(missing)}")
    dist = distribution or packages[0]
    return ProbeResult(available=True, detail="installed", version=module_version(dist))


__all__ = [
    "import_module",
    "module_available",
    "module_version",
    "probe_modules",
]
