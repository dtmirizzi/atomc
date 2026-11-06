"""The Renode plugin: IR -> scripts tool, boot gate and honest matrix-scan gate.

The plugin is deliberately honest about emulation coverage:

* ``renode_generate`` writes ``.repl``/``.resc`` scripts derived from the IR.
* ``gate:fw.renode_boot`` runs Renode headless and reports ``SKIP`` when the binary, MCU or ELF
  artifact is unavailable, ``PASS`` only when a configured boot banner is seen without a fault,
  and ``FAIL`` otherwise with bounded log evidence. It makes no USB-HID claims.
* ``gate:fw.matrix_scan`` is declared but **not implemented**: it always returns ``SKIP`` with a
  HIL requirement, never a fabricated scan.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from atomc_plugin_sdk import PluginManifest, atomc_plugin
from pydantic import ConfigDict

from .analysis import MAX_EVIDENCE_CHARS, classify_boot, tail
from .derive import (
    DEFAULT_TIMEOUT_S,
    DerivationError,
    boot_markers,
    firmware_view,
    generate_scripts,
    unsupported_mcu_reason,
)
from .manifest_data import MANIFEST
from .runner import (
    RenodeRunner,
    SubprocessRenodeRunner,
    find_renode_binary,
    headless_args,
)

MATRIX_SCAN_SKIP_REASON = (
    "GPIO matrix-injection model unproven; requires HIL board + pogo fixture. "
    "Renode does not demonstrate QMK USB HID or per-key reporting, so no scan is claimed."
)

_MANIFEST_FILENAME = "atomc-plugin.json"
_IR_FILENAME = "system_ir.json"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


@runtime_checkable
class PluginContextLike(Protocol):
    """The subset of the daemon/sdk host context the handlers use."""

    @property
    def artifact_root(self) -> Path: ...

    async def ir_get(self, path: str = "/") -> Any: ...

    async def ir_read(self, path: str = "/") -> dict[str, Any]: ...

    async def ir_transact(self, path: str, base_rev: int, ops: list[dict[str, Any]]) -> Any: ...


def manifest_path() -> Path:
    """Locate the committed ``atomc-plugin.json`` (works in the monorepo checkout)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / _MANIFEST_FILENAME
        if candidate.is_file():
            return candidate
    return here.parents[3] / _MANIFEST_FILENAME


def _project_root(start: Path) -> Path | None:
    """Walk up from ``start`` looking for the directory that owns ``system_ir.json``."""
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / _IR_FILENAME).is_file():
            return candidate
    return None


def _slug_for(ir: dict[str, Any]) -> str:
    raw_meta = ir.get("meta")
    meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    raw = meta.get("name") or meta.get("project_id") or "firmware"
    slug = _SLUG_RE.sub("-", str(raw).lower()).strip("-")
    return slug or "firmware"


def _skip(summary: str, evidence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "status": "SKIP",
        "summary": summary,
        "evidence": evidence or [{"kind": "text", "message": summary}],
        "refs": [],
        "suggestions": [],
    }


@dataclass(frozen=True, slots=True)
class _WrittenScripts:
    repl_abs: Path
    resc_abs: Path
    repl_rel: str
    resc_rel: str
    elf_abs: Path
    elf_rel: str


class _PluginManifest(PluginManifest):
    """A manifest that omits unset optional fields when serialised.

    Workaround for a WP-2.2 SDK defect: ``conformance()`` re-validates
    ``manifest.model_dump(mode="json")`` against the shared schema, which rejects the explicit
    ``null`` that pydantic emits for an unset ``runtime.ts`` on a python-only plugin. Omitting the
    unset key matches the contract (the schema expects absent, not null). Remove this subclass if
    the SDK starts dumping with ``exclude_none``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)


_RENODE_MANIFEST = _PluginManifest.model_validate(MANIFEST)


@atomc_plugin(manifest=_RENODE_MANIFEST)
class RenodePlugin:
    """Renode tool + gates. ``runner`` and ``binary_resolver`` are injectable for tests."""

    def __init__(
        self,
        *,
        runner: RenodeRunner | None = None,
        binary_resolver: Any = find_renode_binary,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._runner = runner
        self._resolve_binary = binary_resolver
        self._timeout_s = timeout_s
        # Node handlers consumed by the daemon DAG for the ``renode:generate`` watch.
        self.__atomc_node_handlers__ = {"renode:generate": self.generate_node}

    # -- helpers ------------------------------------------------------------

    def _write_scripts(
        self,
        ctx: PluginContextLike,
        ir: dict[str, Any],
        *,
        timeout_s: float,
    ) -> _WrittenScripts:
        view = firmware_view(ir)
        if not view.elf_path:
            raise DerivationError("no ELF firmware artifact in /firmware")
        slug = _slug_for(ir)
        artifact_root = Path(ctx.artifact_root)
        artifact_root.mkdir(parents=True, exist_ok=True)
        project_root = _project_root(artifact_root)
        base = project_root if project_root is not None else artifact_root

        elf_abs = (base / view.elf_path) if project_root is not None else Path(view.elf_path)
        repl_abs = artifact_root / f"{slug}.repl"
        resc_abs = artifact_root / f"{slug}.resc"

        scripts = generate_scripts(
            ir,
            repl_path=str(repl_abs),
            elf_path=str(elf_abs),
            timeout_s=timeout_s,
        )
        repl_abs.write_text(scripts.repl, encoding="utf-8")
        resc_abs.write_text(scripts.resc, encoding="utf-8")
        return _WrittenScripts(
            repl_abs=repl_abs,
            resc_abs=resc_abs,
            repl_rel=os.path.relpath(repl_abs, base),
            resc_rel=os.path.relpath(resc_abs, base),
            elf_abs=elf_abs,
            elf_rel=view.elf_path,
        )

    # -- gate handlers ------------------------------------------------------

    async def renode_boot(self, ctx: PluginContextLike) -> dict[str, Any]:
        """Run the generated script headless and classify the boot outcome honestly."""
        started = time.perf_counter()
        ir = await ctx.ir_get("/")
        if not isinstance(ir, dict):  # pragma: no cover - defensive
            return _skip("IR root is not a mapping")
        try:
            view = firmware_view(ir)
        except DerivationError as exc:
            return _skip(str(exc))

        reason = unsupported_mcu_reason(view.mcu)
        if reason is not None:
            return _skip(reason, [{"kind": "text", "message": reason}])
        if not view.elf_path:
            return _skip(
                "no ELF firmware artifact in /firmware; run the QMK build "
                "(gate:fw.qmk_compile) first"
            )

        binary = self._resolve_binary()
        if not binary:
            return _skip(
                "renode binary not found (set ATOMC_RENODE_BIN or PYRENODE_PATH, or install Renode)"
            )

        try:
            written = self._write_scripts(ctx, ir, timeout_s=self._timeout_s)
        except DerivationError as exc:
            return _skip(str(exc))

        runner = self._runner or SubprocessRenodeRunner(str(binary))
        args = headless_args(str(binary), written.resc_abs)
        result = runner.run(args, timeout_s=self._timeout_s, cwd=written.resc_abs.parent)
        verdict = classify_boot(result, boot_markers(ir))
        duration_ms = int((time.perf_counter() - started) * 1000)

        evidence: list[dict[str, Any]] = [
            {
                "kind": "json",
                "message": "renode run summary",
                "data": {
                    "target": view.target_id,
                    "mcu": view.mcu,
                    "repl": written.repl_rel,
                    "resc": written.resc_rel,
                    "elf": written.elf_rel,
                    "exit_code": result.exit_code,
                    "timed_out": result.timed_out,
                    "run_ms": result.duration_ms,
                },
            },
            {
                "kind": "text",
                "message": f"renode output (last {MAX_EVIDENCE_CHARS} chars)",
                "data": tail(result.combined_output),
            },
        ]
        return {
            "status": verdict.status,
            "summary": verdict.summary,
            "evidence": evidence,
            "refs": [view.target_id],
            "suggestions": [],
            "duration_ms": duration_ms,
        }

    async def matrix_scan(self, ctx: PluginContextLike) -> dict[str, Any]:
        """Declared-not-implemented: never fabricates a scan; always SKIP."""
        ir = await ctx.ir_get("/")
        refs: list[str] = []
        if isinstance(ir, dict):
            firmware = ir.get("firmware")
            targets = firmware.get("targets") if isinstance(firmware, dict) else None
            if isinstance(targets, list) and targets and isinstance(targets[0], dict):
                target_id = targets[0].get("id")
                if isinstance(target_id, str):
                    refs.append(target_id)
        return {
            "status": "SKIP",
            "summary": MATRIX_SCAN_SKIP_REASON,
            "evidence": [{"kind": "text", "message": MATRIX_SCAN_SKIP_REASON}],
            "refs": refs,
            "suggestions": [],
        }

    # -- tool / node handler ------------------------------------------------

    async def generate(
        self, ctx: PluginContextLike, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """``renode_generate`` tool: write scripts and record their paths under /simulation."""
        return await self._generate(ctx, payload or {})

    async def generate_node(self, ctx: PluginContextLike) -> dict[str, Any]:
        """DAG node handler for the ``renode:generate`` watch (no payload)."""
        return await self._generate(ctx, {})

    async def _generate(self, ctx: PluginContextLike, payload: dict[str, Any]) -> dict[str, Any]:
        ir = await ctx.ir_get("/")
        if not isinstance(ir, dict):  # pragma: no cover - defensive
            return _skip("IR root is not a mapping")
        # A design without a firmware artifact (or with an unsupported MCU) is
        # out of this watch's domain: report an honest SKIP-shaped no-op instead
        # of failing the DAG node. Mirrors the tool/gate skip semantics.
        try:
            view = firmware_view(ir)
        except DerivationError as exc:
            return _skip(str(exc))
        mcu_reason = unsupported_mcu_reason(view.mcu)
        if mcu_reason is not None:
            return _skip(mcu_reason)
        if not view.elf_path:
            return _skip(
                "no ELF firmware artifact in /firmware; run the QMK build "
                "(gate:fw.qmk_compile) first",
            )
        timeout_s = float(payload.get("timeout_s", self._timeout_s))
        written = self._write_scripts(ctx, ir, timeout_s=timeout_s)

        fw_rev: int | None = None
        try:
            fw_info = await ctx.ir_read("/firmware")
            fw_rev = int(fw_info.get("rev", 0))
        except Exception:  # pragma: no cover - host-dependent; IR path optional for the tool
            fw_rev = None

        recorded = False
        try:
            sim_info = await ctx.ir_read("/simulation")
            base_rev = int(sim_info.get("rev", 0))
            value = sim_info.get("value")
            platform = value.get("platform") if isinstance(value, dict) else None
            ops: list[dict[str, Any]] = []
            if isinstance(platform, dict):
                ops.append(
                    {"op": "replace", "path": "/platform/repl_path", "value": written.repl_rel}
                )
                ops.append(
                    {"op": "replace", "path": "/platform/resc_path", "value": written.resc_rel}
                )
                if fw_rev is not None:
                    ops.append(
                        {
                            "op": "replace",
                            "path": "/platform/generated_from_rev",
                            "value": fw_rev,
                        }
                    )
            else:
                platform_value: dict[str, Any] = {
                    "repl_path": written.repl_rel,
                    "resc_path": written.resc_rel,
                }
                if fw_rev is not None:
                    platform_value["generated_from_rev"] = fw_rev
                ops.append({"op": "add", "path": "/platform", "value": platform_value})
            if ops:
                await ctx.ir_transact("/simulation", base_rev, ops)
                recorded = True
        except Exception:
            recorded = False

        return {
            "result": {
                "repl_path": written.repl_rel,
                "resc_path": written.resc_rel,
                "elf_path": written.elf_rel,
                "recorded_in_ir": recorded,
            },
            "artifacts": [
                {"kind": "repl", "path": written.repl_rel},
                {"kind": "resc", "path": written.resc_rel},
            ],
        }


plugin = RenodePlugin
"""Entry-point target: the decorated class, instantiated by the daemon."""

__all__ = ["MATRIX_SCAN_SKIP_REASON", "RenodePlugin", "manifest_path", "plugin"]
