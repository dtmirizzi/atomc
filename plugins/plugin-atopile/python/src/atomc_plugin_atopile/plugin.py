"""The ``plugin:atopile`` implementation: two tools and four gates.

Handler signatures follow the daemon's tolerant invocation: gate handlers take ``(ctx)`` and
tool handlers take ``(ctx, args)``. All IR writes go through the injected context so the daemon
enforces the plugin's ``produces`` scopes.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from atomc_core_ir import GateResult

from .context import PluginContext
from .electrical import extract_electrical, merge_by_id
from .errors import BoardParseError, KiutilsUnavailableError
from .gates import (
    check_assertions,
    check_no_unconnected,
    check_testpad_min_count,
    check_testpad_nets_covered,
)
from .ir import read_value, transact_node
from .manifest import manifest_dict
from .pcb import BoardModel, board_to_layout, load_board
from .runner import CommandRunner, SubprocessRunner, bounded

__all__ = ["AtopilePlugin", "plugin"]

DEFAULT_TARGET = "default"
DEFAULT_TIMEOUT_S = 300


def _tool_result(
    status: str,
    summary: str,
    *,
    available: bool = True,
    evidence: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": status,
        "available": available,
        "summary": summary,
        "evidence": evidence or [],
    }
    result.update(extra)
    return result


def _text_evidence(message: str) -> dict[str, Any]:
    return {"kind": "text", "message": message}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _ids(records: Any) -> set[str]:
    if not isinstance(records, list):
        return set()
    return {
        str(record["id"]) for record in records if isinstance(record, Mapping) and record.get("id")
    }


class AtopilePlugin:
    """atopile compilation, PCB import and ERC gates."""

    def __init__(
        self,
        *,
        runner: CommandRunner | None = None,
        board_loader: Callable[[str | Path], BoardModel] | None = None,
        which: Callable[[str], str | None] | None = None,
    ) -> None:
        # The daemon's entry-point resolver validates ``.manifest`` into its own model; see
        # ``manifest.py`` for why this is a plain dict rather than ``__atomc_manifest__``.
        self.manifest: dict[str, Any] = manifest_dict()
        self.runner: CommandRunner = runner or SubprocessRunner()
        self.board_loader: Callable[[str | Path], BoardModel] = board_loader or load_board
        self.which: Callable[[str], str | None] = which or shutil.which

    # -- tools --------------------------------------------------------------

    async def compile(self, ctx: PluginContext, args: Mapping[str, Any]) -> dict[str, Any]:
        """Run ``ato build`` and write extracted components, nets and assertions."""
        project_dir_raw = args.get("project_dir")
        if not project_dir_raw:
            return _tool_result("FAIL", "compile requires 'project_dir'")
        project_dir = Path(str(project_dir_raw)).expanduser()
        if not project_dir.is_dir():
            return _tool_result("FAIL", f"project_dir does not exist: {project_dir}")

        entry = str(args.get("entry") or "main.ato:App")
        target = str(args.get("target") or DEFAULT_TARGET)
        timeout_s = _timeout(args.get("timeout_s"))

        ato = self.which("ato")
        if ato is None:
            return _tool_result(
                "UNAVAILABLE",
                "'ato' CLI not found on PATH",
                available=False,
                evidence=[_text_evidence("atopile build requires the `ato` CLI (atopile 0.15.9)")],
            )

        argv = [ato, "build"]
        if target != DEFAULT_TARGET:
            argv.extend(["--target", target])
        command = self.runner.run(argv, cwd=project_dir, timeout_s=timeout_s)
        if command.returncode != 0:
            return _tool_result(
                "FAIL",
                f"`ato build` exited {command.returncode}",
                evidence=[
                    _text_evidence(f"command: {' '.join(argv)} (cwd={project_dir})"),
                    _text_evidence(bounded(command.stderr) or bounded(command.stdout)),
                ],
            )

        build_dir = project_dir / "build" / "builds" / target
        bom = _read_json(build_dir / f"{target}.bom.json")
        variables = _read_json(build_dir / f"{target}.variables.ato.json")
        warnings: list[str] = []
        board: BoardModel | None = None
        board_path = _find_board(project_dir)
        if board_path is not None:
            try:
                board = self.board_loader(board_path)
            except KiutilsUnavailableError:
                warnings.append(
                    f"kiutils unavailable: nets/pins not extracted from {board_path.name}"
                )
            except BoardParseError as exc:
                warnings.append(f"board parse failed: {exc}")
        else:
            warnings.append("no .kicad_pcb found in layout/; nets/pins not extracted")
        if bom is None:
            warnings.append(f"bom not found at {build_dir / f'{target}.bom.json'}")
        if bom is None and board is None:
            return _tool_result(
                "FAIL",
                "ato build succeeded but produced no bom.json or kicad_pcb to extract",
                evidence=[_text_evidence(f"build dir: {build_dir}")],
            )

        extracted = extract_electrical(bom=bom, board=board, entry=entry, variables=variables or {})
        existing = _as_dict(await read_value(ctx, "/electrical"))
        updates = {
            "source": extracted["source"],
            "components": merge_by_id(existing.get("components"), extracted["components"]),
            "nets": merge_by_id(existing.get("nets"), extracted["nets"]),
            "assertions": merge_by_id(existing.get("assertions"), extracted["assertions"]),
        }
        try:
            await transact_node(ctx, "/electrical", updates)
        except Exception as exc:  # surfaced as structured evidence
            return _tool_result(
                "FAIL",
                f"could not write /electrical: {type(exc).__name__}: {exc}",
                evidence=[_text_evidence(f"ato build exited 0 but IR write failed: {exc}")],
            )
        return _tool_result(
            "PASS",
            f"ato build succeeded; wrote {len(updates['components'])} components, "
            f"{len(updates['nets'])} nets",
            evidence=[
                _text_evidence(f"`ato build` exited 0 (cwd={project_dir})"),
                {
                    "kind": "json",
                    "data": {
                        "returncode": 0,
                        "components": len(updates["components"]),
                        "nets": len(updates["nets"]),
                        "assertions": len(updates["assertions"]),
                        "board": board is not None,
                        "warnings": warnings,
                    },
                },
            ],
            warnings=warnings,
            components=len(updates["components"]),
            nets=len(updates["nets"]),
        )

    async def import_pcb(self, ctx: PluginContext, args: Mapping[str, Any]) -> dict[str, Any]:
        """Parse a ``.kicad_pcb`` and write outline, placements and test pads to ``/layout``."""
        pcb_raw = args.get("pcb_path")
        if not pcb_raw:
            return _tool_result("FAIL", "import_pcb requires 'pcb_path'")
        pcb_path = Path(str(pcb_raw)).expanduser()

        try:
            board = self.board_loader(pcb_path)
        except KiutilsUnavailableError as exc:
            return _tool_result(
                "UNAVAILABLE",
                "kiutils is not installed; cannot parse .kicad_pcb",
                available=False,
                evidence=[_text_evidence(str(exc))],
            )
        except BoardParseError as exc:
            return _tool_result("FAIL", str(exc), evidence=[_text_evidence(str(exc))])

        electrical = _as_dict(await read_value(ctx, "/electrical"))
        valid_components = _ids(electrical.get("components"))
        valid_nets = _ids(electrical.get("nets"))
        existing_layout = _as_dict(await read_value(ctx, "/layout"))

        try:
            updates = board_to_layout(
                board,
                valid_component_ids=valid_components,
                valid_net_ids=valid_nets,
                existing=existing_layout,
            )
        except BoardParseError as exc:
            return _tool_result("FAIL", str(exc), evidence=[_text_evidence(str(exc))])

        warnings: list[str] = []
        skipped_components = sorted(
            {
                fp.reference
                for fp in board.footprints
                if fp.reference and f"comp:{fp.reference}" not in valid_components
            }
        )
        if skipped_components:
            warnings.append(
                f"{len(skipped_components)} placement(s) skipped (component ids not in /electrical)"
            )
        try:
            await transact_node(ctx, "/layout", updates)
        except Exception as exc:  # surfaced as structured evidence
            return _tool_result(
                "FAIL",
                f"could not write /layout: {type(exc).__name__}: {exc}",
                evidence=[_text_evidence(str(exc))],
            )
        pad_count = len(updates["test_pads"])
        return _tool_result(
            "PASS",
            f"imported {board.path}: {len(updates['placements'])} placements, "
            f"{pad_count} test pads",
            evidence=[
                _text_evidence(f"parsed {board.path} with kiutils"),
                {
                    "kind": "json",
                    "data": {
                        "path": board.path,
                        "placements": len(updates["placements"]),
                        "test_pads": pad_count,
                        "outline_points": len(board.outline),
                        "warnings": warnings,
                    },
                },
            ],
            warnings=warnings,
            placements=len(updates["placements"]),
            test_pads=pad_count,
        )

    # -- gates --------------------------------------------------------------

    async def check_no_unconnected(self, ctx: PluginContext) -> GateResult:
        """``gate:erc.no_unconnected``."""
        return await check_no_unconnected(ctx)

    async def check_assertions(self, ctx: PluginContext) -> GateResult:
        """``gate:erc.assertions``."""
        return await check_assertions(ctx)

    async def check_testpad_min_count(self, ctx: PluginContext) -> GateResult:
        """``gate:layout.testpads.min_count``."""
        return await check_testpad_min_count(ctx)

    async def check_testpad_nets_covered(self, ctx: PluginContext) -> GateResult:
        """``gate:layout.testpads.nets_covered``."""
        return await check_testpad_nets_covered(ctx)


def _timeout(value: Any) -> int:
    try:
        parsed = int(value)
    except TypeError, ValueError:
        return DEFAULT_TIMEOUT_S
    return max(parsed, 1)


def _find_board(project_dir: Path) -> Path | None:
    candidates: Sequence[Path] = sorted((project_dir / "layout").rglob("*.kicad_pcb"))
    if not candidates:
        candidates = sorted(project_dir.rglob("*.kicad_pcb"))
    for candidate in candidates:
        if ".ato" not in candidate.parts and "build" not in candidate.parts:
            return candidate
    return candidates[0] if candidates else None


plugin = AtopilePlugin()
