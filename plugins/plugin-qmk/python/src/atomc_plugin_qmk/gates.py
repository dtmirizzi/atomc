"""QMK derivation gates and tools.

The compile gate is deliberately honest: missing QMK tooling or a missing ``QMK_HOME`` returns
``SKIP`` with evidence and a suggestion. Only a real subprocess exit 0 plus a fresh artifact can
produce ``PASS``. The pure matrix-pin gate always runs and never needs QMK installed.
"""

from __future__ import annotations

import hashlib
import inspect
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from .derivation import DerivationError, derive, materialize
from .manifest import PLUGIN_NAME, PLUGIN_VERSION

__all__ = [
    "CompileOutcome",
    "ToolchainCheck",
    "check_matrix_pins",
    "check_toolchain",
    "compile_gate",
    "compile_qmk",
    "compile_tool",
    "generate_tool",
    "matrix_pins_gate",
    "run_qmk_compile",
]

PLUGIN_ID = f"plugin:{PLUGIN_NAME}@{PLUGIN_VERSION}"
OWNER_AGENT = "fw-agent"
_MAX_OUTPUT = 4000
_ARTIFACT_SUFFIXES = (".bin", ".uf2", ".hex", ".elf")
_ARTIFACT_KINDS = {".bin": "bin", ".uf2": "uf2", ".hex": "hex", ".elf": "elf"}


@dataclass(frozen=True)
class ToolchainCheck:
    """Result of probing for the QMK CLI and a QMK checkout."""

    available: bool
    qmk_path: str | None
    qmk_home: Path
    summary: str | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    suggestions: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class CompileOutcome:
    """Result of a real ``qmk compile`` attempt."""

    status: Literal["PASS", "FAIL", "SKIP"]
    summary: str
    evidence: list[dict[str, Any]]
    suggestions: list[dict[str, Any]]
    duration_ms: int
    artifact_path: Path | None = None
    artifact_id: str | None = None
    artifact_sha256: str | None = None
    artifact_bytes: int | None = None
    artifact_kind: str | None = None
    command: list[str] = field(default_factory=list)
    qmk_home: Path | None = None
    returncode: int | None = None


Runner = Callable[..., subprocess.CompletedProcess[str]]

# Marker file the plugin writes into its installed keyboard copies.
_PLUGIN_MARKER = ".atomc-plugin-qmk"
Which = Callable[[str], str | None]


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _bounded(text: str, limit: int = _MAX_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"...[{omitted} chars truncated]\n{text[-limit:]}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _artifact_id(keyboard_path: str, keymap: str) -> str:
    stem = keyboard_path.replace("/", "_").replace("-", "_")
    return f"art:qmk_{stem}_{keymap}"


def check_toolchain(
    explicit_qmk_home: str | Path | None = None,
    *,
    which: Which | None = None,
) -> ToolchainCheck:
    """Probe for ``qmk`` and the configured QMK checkout without running anything."""
    if which is None:
        which = shutil.which
    raw_home = explicit_qmk_home or os.environ.get("QMK_HOME") or "~/qmk_firmware"
    qmk_home = Path(raw_home).expanduser()
    qmk_path = which("qmk")
    if qmk_path is None:
        return ToolchainCheck(
            available=False,
            qmk_path=None,
            qmk_home=qmk_home,
            summary="qmk CLI not found on PATH; cannot verify firmware compilation",
            evidence=[
                {
                    "kind": "text",
                    "message": "shutil.which('qmk') returned None; qmk was not executed",
                }
            ],
            suggestions=[
                {
                    "message": (
                        "Install the QMK CLI (for example `uv tool install qmk`) and make sure "
                        "`qmk` is on PATH, then rerun this gate."
                    )
                }
            ],
        )
    if not qmk_home.is_dir():
        return ToolchainCheck(
            available=False,
            qmk_path=qmk_path,
            qmk_home=qmk_home,
            summary=f"QMK_HOME={qmk_home} does not exist; cannot verify firmware compilation",
            evidence=[
                {
                    "kind": "text",
                    "message": f"resolved QMK_HOME={qmk_home} is not a directory; qmk was not run",
                }
            ],
            suggestions=[
                {
                    "message": (
                        "Set QMK_HOME to an existing qmk_firmware checkout, or run "
                        "`qmk setup -H <path>` first."
                    )
                }
            ],
        )
    return ToolchainCheck(available=True, qmk_path=qmk_path, qmk_home=qmk_home)


def run_qmk_compile(
    command: list[str],
    *,
    cwd: str,
    env: Mapping[str, str],
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    """Run the QMK CLI. Kept module-level so tests can inject a fake runner."""
    return subprocess.run(
        command,
        cwd=cwd,
        env=dict(env),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _find_artifact(
    qmk_home: Path,
    keyboard_path: str,
    keymap: str,
    *,
    since: float,
) -> Path | None:
    stem = f"{keyboard_path.replace('/', '_')}_{keymap}"
    build_dir = qmk_home / ".build"
    for suffix in _ARTIFACT_SUFFIXES:
        direct = build_dir / f"{stem}{suffix}"
        if direct.is_file() and direct.stat().st_mtime >= since - 2:
            return direct
        if not build_dir.is_dir():
            continue
        candidates = sorted(
            build_dir.rglob(f"{stem}{suffix}"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for candidate in candidates:
            if candidate.is_file() and candidate.stat().st_mtime >= since - 2:
                return candidate
    return None


def _copy_artifact(source: Path, artifact_root: Path, keyboard_path: str) -> Path:
    destination_dir = artifact_root / "firmware" / keyboard_path.replace("/", "_")
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.name
    shutil.copy2(source, destination)
    return destination


def _fail(
    summary: str,
    *,
    duration_ms: int,
    evidence: list[dict[str, Any]] | None = None,
    suggestions: list[dict[str, Any]] | None = None,
    command: list[str] | None = None,
    qmk_home: Path | None = None,
    returncode: int | None = None,
) -> CompileOutcome:
    return CompileOutcome(
        status="FAIL",
        summary=summary,
        evidence=evidence or [{"kind": "text", "message": summary}],
        suggestions=suggestions or [],
        duration_ms=duration_ms,
        command=command or [],
        qmk_home=qmk_home,
        returncode=returncode,
    )


def _skip(
    summary: str,
    *,
    duration_ms: int,
    evidence: list[dict[str, Any]],
    suggestions: list[dict[str, Any]],
    qmk_home: Path | None = None,
) -> CompileOutcome:
    return CompileOutcome(
        status="SKIP",
        summary=summary,
        evidence=evidence,
        suggestions=suggestions,
        duration_ms=duration_ms,
        qmk_home=qmk_home,
    )


def compile_qmk(
    ir: Mapping[str, Any],
    *,
    qmk_home: str | Path | None = None,
    artifact_root: str | Path | None = None,
    keymap: str = "default",
    which: Which | None = None,
    runner: Runner | None = None,
    timeout_s: int = 900,
) -> CompileOutcome:
    """Derive sources and run ``qmk compile`` for the IR keyboard.

    Returns ``SKIP`` when QMK or ``QMK_HOME`` is unavailable, ``FAIL`` for derivation,
    symlink, subprocess or artifact-discovery failures, and ``PASS`` only after a fresh
    artifact has been copied and hashed.
    """
    started = time.perf_counter()
    if runner is None:
        runner = run_qmk_compile
    toolchain = check_toolchain(qmk_home, which=which)
    if not toolchain.available:
        return _skip(
            toolchain.summary or "QMK toolchain unavailable",
            duration_ms=int((time.perf_counter() - started) * 1000),
            evidence=toolchain.evidence,
            suggestions=toolchain.suggestions,
            qmk_home=toolchain.qmk_home,
        )

    try:
        derived = derive(ir, keymap=keymap)
    except DerivationError as exc:
        return _fail(
            f"IR -> QMK derivation failed: {exc}",
            duration_ms=int((time.perf_counter() - started) * 1000),
            evidence=[{"kind": "text", "message": str(exc)}],
            suggestions=[{"message": "Fix the IR /keyboard node and retry the gate."}],
            qmk_home=toolchain.qmk_home,
        )

    root = (
        Path(artifact_root)
        if artifact_root is not None
        else Path(tempfile.mkdtemp(prefix="atomc-qmk-"))
    )
    staging = root / "qmk"
    try:
        materialize(derived, staging)
    except OSError as exc:
        return _fail(
            f"could not write derived QMK sources under {staging}: {exc}",
            duration_ms=int((time.perf_counter() - started) * 1000),
            evidence=[{"kind": "text", "message": str(exc)}],
            qmk_home=toolchain.qmk_home,
        )

    keyboard_path = derived.keyboard_path
    target = toolchain.qmk_home / "keyboards" / keyboard_path
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # qmk's keyboard enumeration does not follow symlinked keyboard folders, so
        # the plugin installs a real directory copy and marks it as its own.
        if target.is_symlink() or (target.exists() and (target / _PLUGIN_MARKER).is_file()):
            if target.is_symlink() and not target.is_dir():
                target.unlink()
            else:
                shutil.rmtree(target)
        elif target.exists():
            return _fail(
                f"refusing to replace non-plugin {target}",
                duration_ms=int((time.perf_counter() - started) * 1000),
                evidence=[
                    {
                        "kind": "text",
                        "message": (
                            f"{target} exists and is not plugin-managed (no {_PLUGIN_MARKER}); "
                            "the plugin only replaces its own keyboard copies"
                        ),
                    }
                ],
                suggestions=[
                    {
                        "message": (
                            "Move or remove the existing keyboard directory, then rerun the gate."
                        )
                    }
                ],
                qmk_home=toolchain.qmk_home,
            )
        shutil.copytree(staging / "keyboards" / keyboard_path, target)
        (target / _PLUGIN_MARKER).write_text("managed by atomc-plugin-qmk\n", encoding="utf-8")
    except OSError as exc:
        return _fail(
            f"could not install {target} into QMK_HOME: {exc}",
            duration_ms=int((time.perf_counter() - started) * 1000),
            evidence=[{"kind": "text", "message": str(exc)}],
            qmk_home=toolchain.qmk_home,
        )

    command = [
        toolchain.qmk_path or "qmk",
        "compile",
        "-kb",
        keyboard_path,
        "-km",
        keymap,
    ]
    env = os.environ.copy()
    env["QMK_HOME"] = str(toolchain.qmk_home)
    compile_started = time.perf_counter()
    try:
        completed = runner(
            command,
            cwd=str(toolchain.qmk_home),
            env=env,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        duration = int((time.perf_counter() - started) * 1000)
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return _fail(
            f"qmk compile timed out after {timeout_s}s",
            duration_ms=duration,
            evidence=[{"kind": "text", "message": _bounded(stdout + stderr)}],
            suggestions=[{"message": "Inspect the compiler output and retry the gate."}],
            command=command,
            qmk_home=toolchain.qmk_home,
        )
    except Exception as exc:
        return _fail(
            f"qmk compile could not start: {type(exc).__name__}: {exc}",
            duration_ms=int((time.perf_counter() - started) * 1000),
            evidence=[{"kind": "text", "message": _bounded(str(exc))}],
            command=command,
            qmk_home=toolchain.qmk_home,
        )

    duration = int((time.perf_counter() - started) * 1000)
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    output = _bounded(stdout + stderr)
    if completed.returncode != 0:
        return _fail(
            f"qmk compile failed with exit code {completed.returncode}",
            duration_ms=duration,
            evidence=[
                {"kind": "text", "message": output or "(no compiler output captured)"},
                {"kind": "json", "data": {"command": command, "returncode": completed.returncode}},
            ],
            suggestions=[{"message": "Fix the reported compiler error and rerun the gate."}],
            command=command,
            qmk_home=toolchain.qmk_home,
            returncode=completed.returncode,
        )

    artifact = _find_artifact(
        toolchain.qmk_home,
        keyboard_path,
        keymap,
        since=compile_started,
    )
    if artifact is None:
        return _fail(
            "qmk compile exited 0 but no fresh .bin/.uf2/.hex/.elf artifact was found",
            duration_ms=duration,
            evidence=[
                {"kind": "text", "message": output or "(no compiler output captured)"},
                {
                    "kind": "json",
                    "data": {
                        "command": command,
                        "searched": str(toolchain.qmk_home / ".build"),
                        "stem": f"{keyboard_path.replace('/', '_')}_{keymap}",
                    },
                },
            ],
            suggestions=[
                {
                    "message": (
                        "Check that QMK wrote the firmware under QMK_HOME/.build and that the "
                        "keyboard name matches keyboard.qmk.keyboard_path."
                    )
                }
            ],
            command=command,
            qmk_home=toolchain.qmk_home,
            returncode=completed.returncode,
        )

    try:
        destination = _copy_artifact(artifact, root, keyboard_path)
        sha256 = _sha256_file(destination)
        size = destination.stat().st_size
    except OSError as exc:
        return _fail(
            f"qmk compile succeeded but the artifact could not be copied: {exc}",
            duration_ms=duration,
            evidence=[{"kind": "text", "message": str(exc)}],
            command=command,
            qmk_home=toolchain.qmk_home,
            returncode=completed.returncode,
        )

    kind = _ARTIFACT_KINDS.get(destination.suffix.lower(), "other")
    artifact_id = _artifact_id(keyboard_path, keymap)
    summary = (
        f"qmk compile succeeded for {keyboard_path}/{keymap}; "
        f"{destination.name} {sha256} ({size} B)"
    )
    return CompileOutcome(
        status="PASS",
        summary=summary,
        evidence=[
            {"kind": "text", "message": output or "qmk compile exited 0"},
            {
                "kind": "artifact",
                "ref": artifact_id,
                "message": str(destination),
                "data": {"sha256": sha256, "bytes": size, "kind": kind},
            },
        ],
        suggestions=[],
        duration_ms=duration,
        artifact_path=destination,
        artifact_id=artifact_id,
        artifact_sha256=sha256,
        artifact_bytes=size,
        artifact_kind=kind,
        command=command,
        qmk_home=toolchain.qmk_home,
        returncode=completed.returncode,
    )


def _artifact_record(outcome: CompileOutcome) -> dict[str, Any]:
    assert outcome.artifact_path is not None
    assert outcome.artifact_id is not None
    assert outcome.artifact_sha256 is not None
    assert outcome.artifact_bytes is not None
    return {
        "id": outcome.artifact_id,
        "kind": outcome.artifact_kind or "other",
        "path": str(outcome.artifact_path),
        "sha256": outcome.artifact_sha256,
        "bytes": outcome.artifact_bytes,
        "produced_by": PLUGIN_ID,
        "produced_at": _now(),
    }


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _read_node(ctx: Any, path: str) -> tuple[int, Any | None]:
    try:
        if hasattr(ctx, "ir_read"):
            raw = await _maybe_await(ctx.ir_read(path))
            if isinstance(raw, dict) and "rev" in raw and "value" in raw:
                return int(raw["rev"]), raw["value"]
        raw = await _maybe_await(ctx.ir_get(path))
        if hasattr(raw, "rev") and hasattr(raw, "value"):
            return int(raw.rev), raw.value
        return 0, raw
    except Exception as exc:
        message = str(exc).lower()
        if "not present" in message or "not found" in message:
            return 0, None
        raise


def _gate_result(
    *,
    gate_id: str,
    status: Literal["PASS", "FAIL", "SKIP"],
    summary: str,
    evidence: list[dict[str, Any]],
    suggestions: list[dict[str, Any]],
    ir_rev: int,
    duration_ms: int,
    refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": gate_id,
        "status": status,
        "severity": "blocking",
        "plugin": PLUGIN_ID,
        "owner_agent": OWNER_AGENT,
        "evaluated_at": _now(),
        "ir_rev": ir_rev,
        "duration_ms": max(0, duration_ms),
        "summary": summary,
        "evidence": evidence,
        "suggestions": suggestions,
        "refs": refs or [],
    }


def check_matrix_pins(
    ir: Mapping[str, Any],
    generated_keyboard: Mapping[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    """Check generated ``matrix_pins`` against the IR matrix pins."""
    try:
        keyboard = ir.get("keyboard")
        if not isinstance(keyboard, dict):
            return False, ["IR has no /keyboard node"]
        matrix = keyboard.get("matrix")
        if not isinstance(matrix, dict):
            return False, ["IR keyboard.matrix is missing"]
        generated = (
            dict(generated_keyboard) if generated_keyboard is not None else _derive_keyboard(ir)
        )
        pins = generated.get("matrix_pins")
        if not isinstance(pins, dict):
            return False, ["generated keyboard.json has no matrix_pins object"]
        problems: list[str] = []
        if pins.get("rows") != matrix.get("row_pins"):
            problems.append(
                f"row pins {pins.get('rows')!r} do not match IR {matrix.get('row_pins')!r}"
            )
        if pins.get("cols") != matrix.get("col_pins"):
            problems.append(
                f"col pins {pins.get('cols')!r} do not match IR {matrix.get('col_pins')!r}"
            )
        return not problems, problems
    except DerivationError as exc:
        return False, [str(exc)]


def _derive_keyboard(ir: Mapping[str, Any]) -> dict[str, Any]:
    from .derivation import derive_keyboard_json

    return derive_keyboard_json(ir)


async def matrix_pins_gate(ctx: Any) -> dict[str, Any]:
    """Gate handler: pure check that generated matrix pins match IR pins."""
    started = time.perf_counter()
    gate_id = "gate:fw.matrix_pins_match_ir"
    try:
        rev, document = await _read_node(ctx, "/")
        keyboard = document.get("keyboard") if isinstance(document, dict) else None
    except Exception as exc:
        return _gate_result(
            gate_id=gate_id,
            status="FAIL",
            summary=f"could not read the IR document: {type(exc).__name__}: {exc}",
            evidence=[{"kind": "text", "message": str(exc)}],
            suggestions=[],
            ir_rev=0,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    if not isinstance(keyboard, dict):
        # A design without a /keyboard node is simply not a keyboard design:
        # the gate is not applicable rather than failing.
        return _gate_result(
            gate_id=gate_id,
            status="SKIP",
            summary="IR has no /keyboard node; this gate applies to keyboard designs",
            evidence=[
                {
                    "kind": "text",
                    "message": (
                        "the /keyboard node is absent; no matrix pins exist to check"
                    ),
                }
            ],
            suggestions=[],
            ir_rev=rev,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    ok, problems = check_matrix_pins({"keyboard": keyboard})
    if ok:
        summary = "generated QMK matrix pins match the IR row/col pins"
        evidence = [
            {
                "kind": "json",
                "data": {
                    "rows": keyboard["matrix"]["row_pins"],
                    "cols": keyboard["matrix"]["col_pins"],
                },
            }
        ]
        suggestions: list[dict[str, Any]] = []
        status: Literal["PASS", "FAIL"] = "PASS"
    else:
        summary = "generated QMK matrix pins do not match the IR"
        evidence = [{"kind": "text", "message": problem} for problem in problems]
        suggestions = [
            {
                "message": (
                    "Fix the derivation or the IR matrix pins; both must agree before flashing."
                )
            }
        ]
        status = "FAIL"
    return _gate_result(
        gate_id=gate_id,
        status=status,
        summary=summary,
        evidence=evidence,
        suggestions=suggestions,
        ir_rev=rev,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


async def _record_artifact(ctx: Any, outcome: CompileOutcome) -> str | None:
    """Write the compiled artifact into ``/firmware``; return an error message on failure."""
    artifact = _artifact_record(outcome)
    try:
        rev, firmware = await _read_node(ctx, "/firmware")
    except Exception as exc:
        return f"could not read /firmware: {type(exc).__name__}: {exc}"

    if not isinstance(firmware, dict):
        value = {
            "_meta": {"rev": 0, "lock": None},
            "targets": [
                {
                    "id": "fw:main",
                    "mcu": "STM32F411CEU6",
                    "core": "cortex-m4f",
                    "memory": [],
                    "framework": "qmk",
                    "source_dir": "qmk",
                    "build_cmd": "qmk compile",
                    "artifacts": [artifact],
                }
            ],
            "peripherals": [],
            "suites": [],
        }
        ops = [{"op": "add", "path": "", "value": value}]
        base_rev = rev
    else:
        targets = firmware.get("targets")
        target_list: list[Any] = targets if isinstance(targets, list) else []
        qmk_index = next(
            (
                index
                for index, target in enumerate(target_list)
                if isinstance(target, dict)
                and (target.get("framework") == "qmk" or target.get("id") == "fw:main")
            ),
            None,
        )
        if qmk_index is not None:
            target = target_list[qmk_index]
            artifacts = target.get("artifacts") if isinstance(target, dict) else None
            existing = artifacts if isinstance(artifacts, list) else []
            kept: list[Any] = [
                item
                for item in existing
                if not (isinstance(item, dict) and item.get("id") == artifact["id"])
            ]
            value_list: list[Any] = [*kept, artifact]
            ops = [
                {
                    "op": "add",
                    "path": f"/targets/{qmk_index}/artifacts",
                    "value": value_list,
                }
            ]
        else:
            used = {
                target.get("id")
                for target in target_list
                if isinstance(target, dict) and isinstance(target.get("id"), str)
            }
            target_id = "fw:main" if "fw:main" not in used else "fw:qmk"
            suffix = 2
            while target_id in used:
                target_id = f"fw:qmk_{suffix}"
                suffix += 1
            ops = [
                {
                    "op": "add",
                    "path": "/targets/-",
                    "value": {
                        "id": target_id,
                        "mcu": "STM32F411CEU6",
                        "core": "cortex-m4f",
                        "memory": [],
                        "framework": "qmk",
                        "source_dir": "qmk",
                        "build_cmd": "qmk compile",
                        "artifacts": [artifact],
                    },
                }
            ]
        base_rev = rev

    try:
        await _maybe_await(ctx.ir_transact("/firmware", base_rev, ops))
    except Exception as exc:
        return f"/firmware transaction failed: {type(exc).__name__}: {exc}"
    return None


async def compile_gate(ctx: Any) -> dict[str, Any]:
    """Gate handler: run ``qmk compile`` and record a real artifact on PASS."""
    started = time.perf_counter()
    gate_id = "gate:fw.qmk_compile"
    toolchain = check_toolchain()
    if not toolchain.available:
        return _gate_result(
            gate_id=gate_id,
            status="SKIP",
            summary=toolchain.summary or "QMK toolchain unavailable",
            evidence=toolchain.evidence,
            suggestions=toolchain.suggestions,
            ir_rev=0,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    try:
        rev, document = await _read_node(ctx, "/")
        keyboard = document.get("keyboard") if isinstance(document, dict) else None
    except Exception as exc:
        return _gate_result(
            gate_id=gate_id,
            status="FAIL",
            summary=f"could not read the IR document: {type(exc).__name__}: {exc}",
            evidence=[{"kind": "text", "message": str(exc)}],
            suggestions=[],
            ir_rev=0,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    if not isinstance(keyboard, dict):
        # A design without a /keyboard node is not a keyboard design: the gate
        # is not applicable rather than a firmware failure.
        return _gate_result(
            gate_id=gate_id,
            status="SKIP",
            summary="IR has no /keyboard node; this gate applies to keyboard designs",
            evidence=[
                {
                    "kind": "text",
                    "message": (
                        "the /keyboard node is absent; there is no firmware to compile"
                    ),
                }
            ],
            suggestions=[],
            ir_rev=rev,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    artifact_root = _artifact_root(ctx)
    document = document if isinstance(document, dict) else {"keyboard": keyboard}
    outcome = compile_qmk(document, qmk_home=toolchain.qmk_home, artifact_root=artifact_root)
    evidence = list(outcome.evidence)
    suggestions = list(outcome.suggestions)
    summary = outcome.summary
    status: Literal["PASS", "FAIL", "SKIP"] = outcome.status
    if status == "PASS":
        write_error = await _record_artifact(ctx, outcome)
        if write_error is not None:
            status = "FAIL"
            summary = f"qmk compile succeeded but recording /firmware failed: {write_error}"
            evidence.append({"kind": "text", "message": write_error})
            suggestions.append(
                {"message": "Unlock /firmware or fix the IR write scope and rerun the gate."}
            )
    return _gate_result(
        gate_id=gate_id,
        status=status,
        summary=summary,
        evidence=evidence,
        suggestions=suggestions,
        ir_rev=rev,
        duration_ms=outcome.duration_ms or int((time.perf_counter() - started) * 1000),
        refs=[outcome.artifact_id] if outcome.artifact_id else [],
    )


def _artifact_root(ctx: Any) -> Path:
    root = getattr(ctx, "artifact_root", None)
    if callable(root):
        root = root()
    if root is None:
        return Path(tempfile.mkdtemp(prefix="atomc-qmk-"))
    return Path(root)


async def generate_tool(ctx: Any, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Tool handler: derive QMK sources without running QMK."""
    started = time.perf_counter()
    args = payload or {}
    keymap = str(args.get("keymap") or "default")
    try:
        rev, document = await _read_node(ctx, "/")
        keyboard = document.get("keyboard") if isinstance(document, dict) else None
    except Exception as exc:
        return {
            "status": "FAIL",
            "summary": f"could not read the IR document: {type(exc).__name__}: {exc}",
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
    if not isinstance(keyboard, dict):
        return {
            "status": "SKIP",
            "summary": "IR has no /keyboard node; this applies to keyboard designs",
            "detail": "the /keyboard node is absent; there is nothing to derive",
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
    try:
        document = document if isinstance(document, dict) else {"keyboard": keyboard}
        derived = derive(document, keymap=keymap)
        root = _artifact_root(ctx)
        written = materialize(derived, root / "qmk")
    except (DerivationError, OSError) as exc:
        return {
            "status": "FAIL",
            "summary": f"IR -> QMK derivation failed: {exc}",
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
    ok, problems = check_matrix_pins({"keyboard": keyboard})
    return {
        "status": "PASS",
        "summary": f"derived {len(written)} QMK files for {derived.keyboard_path}",
        "keyboard_path": derived.keyboard_path,
        "keymap": keymap,
        "ir_rev": rev,
        "matrix_pins_match_ir": ok,
        "matrix_pin_problems": problems,
        "files": {relative: str(path) for relative, path in written.items()},
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }


async def compile_tool(ctx: Any, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Tool handler: derive and compile, then record the artifact when successful."""
    started = time.perf_counter()
    args = payload or {}
    keymap = str(args.get("keymap") or "default")
    qmk_home = args.get("qmk_home")
    try:
        rev, document = await _read_node(ctx, "/")
        keyboard = document.get("keyboard") if isinstance(document, dict) else None
    except Exception as exc:
        return {
            "status": "FAIL",
            "summary": f"could not read the IR document: {type(exc).__name__}: {exc}",
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
    if not isinstance(keyboard, dict):
        return {
            "status": "SKIP",
            "summary": "IR has no /keyboard node; this applies to keyboard designs",
            "detail": "the /keyboard node is absent; there is nothing to derive",
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
    document = document if isinstance(document, dict) else {"keyboard": keyboard}
    outcome = compile_qmk(
        document,
        qmk_home=str(qmk_home) if qmk_home else None,
        artifact_root=_artifact_root(ctx),
        keymap=keymap,
    )
    result: dict[str, Any] = {
        "status": outcome.status,
        "summary": outcome.summary,
        "evidence": outcome.evidence,
        "suggestions": outcome.suggestions,
        "duration_ms": outcome.duration_ms,
        "ir_rev": rev,
    }
    if outcome.status == "PASS":
        write_error = await _record_artifact(ctx, outcome)
        if write_error is not None:
            result["status"] = "FAIL"
            result["summary"] = (
                f"qmk compile succeeded but recording /firmware failed: {write_error}"
            )
            result["evidence"] = [*outcome.evidence, {"kind": "text", "message": write_error}]
        else:
            result["artifact"] = _artifact_record(outcome)
    return result
