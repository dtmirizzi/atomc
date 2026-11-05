"""build123d/OCP engine executed inside the supervised worker process.

This module is imported *in the child* only. It imports build123d/OCP lazily inside ``handle`` so
constructing the engine (and therefore the worker startup handshake) stays cheap and never fails
merely because the toolchain is missing — the failure is surfaced as a structured worker error
when an operation actually needs the engine.

Geometry crosses the process boundary by STEP artifact path; only small JSON metadata is sent
back over the pipe.
"""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any


def _dist_version(distribution: str) -> str | None:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return None


class OcpEngine:
    """Operations exposed to :class:`atomcd.kernels.ocp.OcpKernel`."""

    def __init__(self) -> None:
        self._part: Any = None

    def handle(self, op: str, kwargs: dict[str, Any]) -> Any:
        if op == "ping":
            return {"pong": True, "pid": os.getpid()}
        if op == "version":
            return {
                "build123d": _dist_version("build123d"),
                "ocp": _dist_version("cadquery-ocp"),
                "pid": os.getpid(),
            }
        if op == "make_box":
            return self._make_box(
                float(kwargs["length"]),
                float(kwargs["width"]),
                float(kwargs["height"]),
            )
        if op == "export_step":
            return self._export_step(str(kwargs["path"]))
        raise ValueError(f"unknown OCP op {op!r}")

    def close(self) -> None:
        self._part = None

    def _make_box(self, length: float, width: float, height: float) -> dict[str, Any]:
        from build123d import Box  # type: ignore[import-not-found]  # lazy: child-only

        part = Box(length, width, height)
        self._part = part
        return {
            "volume_mm3": round(float(part.volume), 6),
            "bbox_mm": [round(float(v), 6) for v in part.bounding_box().size],
        }

    def _export_step(self, path: str) -> dict[str, Any]:
        if self._part is None:
            raise RuntimeError("no part to export; call make_box first")
        from build123d import export_step  # lazy: child-only heavy import

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        export_step(self._part, str(target))
        return {"path": str(target), "bytes": target.stat().st_size}


def make_engine() -> OcpEngine:
    """Zero-argument engine factory resolved inside the worker process."""
    return OcpEngine()


__all__ = ["OcpEngine", "make_engine"]
