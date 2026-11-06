"""The cad-jig atomc plugin: mechanical gates and the ``cad.generate`` tool.

Gate handlers are thin async adapters that read the system IR through the plugin host, derive
the parametric models and delegate to the pure checks in :mod:`atomc_plugin_cad_jig.gates`.
``cad.generate`` is the only handler that may touch build123d, and it reports an explicit
unavailable result — never a fabricated artifact — when the CAD toolchain is missing.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atomc_plugin_sdk import load_manifest, validate_manifest

from .cad import CadUnavailableError, build123d_available, build_and_export
from .errors import ModelDerivationError
from .gates import (
    check_case_usb_cutout_aligned,
    check_enclosure_clearance,
    check_jig_no_collision,
    check_plate_switch_cutouts,
    check_pogo_spacing,
)
from .models import MechanicalModels, derive_models

PLUGIN_VERSION = "0.1.0"
PRODUCED_BY = f"plugin:cad-jig@{PLUGIN_VERSION}"
MANIFEST_PATH = Path(__file__).with_name("atomc-plugin.json")
MANIFEST = load_manifest(MANIFEST_PATH)
MANIFEST_DICT: dict[str, Any] = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
# Re-validate the mapping so the exported dict and the typed model cannot drift.
validate_manifest(MANIFEST_DICT)

DEFAULT_TARGETS = ("plate", "case", "jig")
DEFAULT_FORMATS = ("step", "stl")
ALLOWED_TARGETS = frozenset({"plate", "case", "jig", "pcb"})
ALLOWED_FORMATS = frozenset({"step", "stl"})


def _skip(field: str, message: str) -> dict[str, Any]:
    return {
        "status": "SKIP",
        "summary": f"cannot derive the mechanical model: {field}: {message}",
        "evidence": [
            {
                "kind": "text",
                "message": (
                    f"the /layout or /mechanical IR is missing or contradictory at {field}: "
                    f"{message}"
                ),
            }
        ],
        "suggestions": [
            {"message": f"provide valid {field} data (e.g. from atopile layout import)"}
        ],
        "refs": [],
    }


async def _read_ir(ctx: Any, path: str = "/") -> Any:
    """Read an IR subtree through either the daemon context or the SDK host protocol."""
    reader = ctx.ir_get
    result = reader(path)
    if inspect.isawaitable(result):
        result = await result
    if hasattr(result, "value") and hasattr(result, "rev"):
        return result.value
    return result


async def _read_rev(ctx: Any, path: str) -> tuple[int, Any]:
    """Read a subtree with its revision, normalizing both host shapes."""
    if hasattr(ctx, "ir_read"):
        raw = ctx.ir_read(path)
        if inspect.isawaitable(raw):
            raw = await raw
        if isinstance(raw, Mapping) and "rev" in raw and "value" in raw:
            return int(raw["rev"]), raw["value"]
    value = await _read_ir(ctx, path)
    rev = 0
    if isinstance(value, Mapping):
        meta = value.get("_meta")
        if isinstance(meta, Mapping) and isinstance(meta.get("rev"), int):
            rev = int(meta["rev"])
    return rev, value


async def _transact(ctx: Any, path: str, base_rev: int, ops: list[dict[str, Any]]) -> Any:
    writer = ctx.ir_transact
    result = writer(path, base_rev, ops)
    if inspect.isawaitable(result):
        result = await result
    return result


def _derive(ir: Any) -> tuple[MechanicalModels | None, ModelDerivationError | None]:
    if not isinstance(ir, Mapping):
        return None, ModelDerivationError("/", "IR root is not an object")
    try:
        return derive_models(ir), None
    except ModelDerivationError as exc:
        return None, exc


def _utcnow() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _artifact_ref(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()


class CadJigPlugin:
    """Mechanical model derivation, gates and STEP/STL generation.

    ``__atomc_manifest__`` is exposed as the raw manifest mapping (not the SDK's pydantic model)
    because the daemon's discovery validates it with its own strict ``Manifest`` model; the SDK's
    ``conformance``/``get_manifest`` helpers accept a mapping too. The manifest is still fully
    validated against the shared JSON Schema at import time via ``validate_manifest``.
    """

    __atomc_manifest__ = MANIFEST_DICT

    async def check_plate_switch_cutouts(self, ctx: Any) -> dict[str, Any]:
        """Gate: switch cutouts are 14 mm on a 19.05 mm grid."""
        models, error = _derive(await _read_ir(ctx))
        if models is None:
            assert error is not None
            return _skip(error.field, str(error).split(": ", 1)[-1])
        return check_plate_switch_cutouts(models)

    async def check_case_usb_cutout_aligned(self, ctx: Any) -> dict[str, Any]:
        """Gate: the USB-C cutout aligns with the connector on its board edge."""
        models, error = _derive(await _read_ir(ctx))
        if models is None:
            assert error is not None
            return _skip(error.field, str(error).split(": ", 1)[-1])
        return check_case_usb_cutout_aligned(models)

    async def check_pogo_spacing(self, ctx: Any) -> dict[str, Any]:
        """Gate: pogo receptacle pitch is at least 2.54 mm."""
        models, error = _derive(await _read_ir(ctx))
        if models is None:
            assert error is not None
            return _skip(error.field, str(error).split(": ", 1)[-1])
        return check_pogo_spacing(models)

    async def check_jig_no_collision(self, ctx: Any) -> dict[str, Any]:
        """Gate: pogo drills and alignment pins clear the 2D board footprint."""
        models, error = _derive(await _read_ir(ctx))
        if models is None:
            assert error is not None
            return _skip(error.field, str(error).split(": ", 1)[-1])
        return check_jig_no_collision(models)

    async def check_enclosure_clearance(self, ctx: Any) -> dict[str, Any]:
        """Gate: the tray walls clear the components."""
        models, error = _derive(await _read_ir(ctx))
        if models is None:
            assert error is not None
            return _skip(error.field, str(error).split(": ", 1)[-1])
        return check_enclosure_clearance(models)

    async def generate(self, ctx: Any, payload: Any = None) -> dict[str, Any]:
        """Tool: build plate/case/jig solids and export STEP/STL artifacts.

        Returns an explicit ``unavailable`` result when build123d is not installed; artifacts are
        recorded in ``/mechanical`` only after they exist on disk.
        """
        args: Mapping[str, Any] = payload if isinstance(payload, Mapping) else {}
        targets = _string_list(args.get("targets"), DEFAULT_TARGETS, ALLOWED_TARGETS, "targets")
        formats = _string_list(args.get("formats"), DEFAULT_FORMATS, ALLOWED_FORMATS, "formats")
        if not build123d_available():
            return {
                "status": "unavailable",
                "reason": "build123d_missing",
                "targets": list(targets),
                "formats": list(formats),
                "artifacts": [],
                "evidence": [
                    {
                        "kind": "text",
                        "message": "build123d is not importable; no STEP/STL was generated",
                    }
                ],
            }
        ir = await _read_ir(ctx)
        models, error = _derive(ir)
        if models is None:
            assert error is not None
            return {
                "status": "error",
                "reason": "model_derivation_failed",
                "evidence": [{"kind": "text", "message": str(error)}],
                "artifacts": [],
            }
        output_dir = _output_dir(ctx, args.get("output_dir"))
        try:
            descriptors = build_and_export(
                models, targets=list(targets), formats=list(formats), output_dir=output_dir
            )
        except CadUnavailableError as exc:  # pragma: no cover - guarded above
            return {
                "status": "unavailable",
                "reason": "build123d_missing",
                "evidence": [{"kind": "text", "message": str(exc)}],
                "artifacts": [],
            }
        artifacts = [
            {
                "id": f"art:cad-{descriptor['target']}-{descriptor['kind']}",
                "kind": descriptor["kind"],
                "path": _artifact_ref(descriptor["path"]),
                "sha256": descriptor["sha256"],
                "bytes": descriptor["bytes"],
                "produced_by": PRODUCED_BY,
                "produced_at": _utcnow(),
            }
            for descriptor in descriptors
        ]
        await _record_artifacts(ctx, artifacts)
        return {
            "status": "ok",
            "targets": list(targets),
            "formats": list(formats),
            "artifacts": artifacts,
        }


def _string_list(
    value: Any,
    default: tuple[str, ...],
    allowed: frozenset[str],
    field: str,
) -> tuple[str, ...]:
    if value is None:
        return default
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError(f"{field} must be a non-empty array")
    selected: list[str] = []
    for item in value:
        if not isinstance(item, str) or item not in allowed:
            raise ValueError(f"{field} entry {item!r} is not one of {sorted(allowed)}")
        if item not in selected:
            selected.append(item)
    return tuple(selected)


def _output_dir(ctx: Any, value: Any) -> Path:
    if value is not None:
        if not isinstance(value, str) or not value or value.startswith("/") or ".." in value:
            raise ValueError("output_dir must be a relative path inside the artifact directory")
        base = Path(ctx.artifact_root)
        return base / value
    artifact_path = getattr(ctx, "artifact_path", None)
    if callable(artifact_path):
        return Path(artifact_path("cad"))
    return Path(ctx.artifact_root) / "cad"


async def _record_artifacts(ctx: Any, artifacts: list[dict[str, Any]]) -> None:
    try:
        rev, mechanical = await _read_rev(ctx, "/mechanical")
    except Exception:
        return
    existing: list[dict[str, Any]] = []
    if isinstance(mechanical, Mapping):
        raw = mechanical.get("artifacts")
        if isinstance(raw, list):
            existing = [item for item in raw if isinstance(item, dict)]
    new_ids = {artifact["id"] for artifact in artifacts}
    merged = [item for item in existing if item.get("id") not in new_ids] + artifacts
    try:
        await _transact(
            ctx,
            "/mechanical",
            rev,
            [{"op": "replace", "path": "/artifacts", "value": merged}],
        )
    except Exception:
        # Artifact recording is best effort; the files exist and the result still reports them.
        return


plugin = CadJigPlugin()


__all__ = [
    "MANIFEST",
    "MANIFEST_DICT",
    "PLUGIN_VERSION",
    "PRODUCED_BY",
    "CadJigPlugin",
    "plugin",
]
