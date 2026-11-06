"""Pure derivation of Renode scripts from the unified IR.

This module has no side effects and no Renode dependency: given the same IR mapping it returns
byte-identical ``.repl``/``.resc`` text. The generated platform description reuses Renode's
generic STM32F4 model (``platforms/cpus/stm32f4.repl``) and documents — as comments — the GPIO
ports and UART/peripheral addresses the firmware (QMK/ChibiOS) is expected to touch. It never
claims a peripheral behaviour the model does not have.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

DEFAULT_TIMEOUT_S = 5.0
"""Default run window for a generated ``.resc`` (seconds)."""

RENODE_BASE_PLATFORM = "platforms/cpus/stm32f4.repl"
"""Renode-shipped generic STM32F4 platform description used as the base."""

SUPPORTED_MCU_PREFIXES = ("STM32F411",)
"""MCUs whose peripheral set is covered by :data:`RENODE_BASE_PLATFORM` for boot purposes."""

# "atomc" is deliberately absent: it is the project name and appears in script paths,
# which would satisfy a substring match without any firmware booting.
DEFAULT_BOOT_MARKERS = ("QMK",)
"""Substrings that count as a firmware boot banner in captured output."""


class DerivationError(ValueError):
    """The IR does not carry enough information to derive a platform (e.g. no firmware target)."""


@dataclass(frozen=True, slots=True)
class MatrixView:
    """Keyboard matrix pins needed to wire/inspect the GPIO model."""

    rows: tuple[str, ...]
    cols: tuple[str, ...]
    diode_direction: str


@dataclass(frozen=True, slots=True)
class PeripheralView:
    """A firmware peripheral with optional base address and named signals."""

    id: str
    kind: str
    base_address: int | None
    signals: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class FirmwareView:
    """The subset of ``/firmware`` the platform derivation needs."""

    target_id: str
    mcu: str
    core: str
    framework: str
    elf_path: str | None
    memory: tuple[tuple[str, int, int], ...] = ()


@dataclass(frozen=True, slots=True)
class GeneratedScripts:
    """Deterministic script text plus the facts used to produce it."""

    repl: str
    resc: str
    target_id: str
    mcu: str
    matrix: MatrixView | None
    peripherals: tuple[PeripheralView, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Small mapping helpers (the IR may arrive as a plain JSON mapping)
# ---------------------------------------------------------------------------


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


def firmware_view(ir: Mapping[str, Any]) -> FirmwareView:
    """Extract the first firmware target. Raises :class:`DerivationError` when absent."""
    firmware = _mapping(ir.get("firmware"))
    targets = _sequence(firmware.get("targets"))
    if not targets:
        raise DerivationError("IR /firmware has no targets; cannot derive a Renode platform")
    target = _mapping(targets[0])
    target_id = _text(target.get("id")) or "fw:main"
    mcu = _text(target.get("mcu")) or ""
    if not mcu:
        raise DerivationError(f"firmware target {target_id!r} has no MCU; cannot pick a platform")
    memory: list[tuple[str, int, int]] = []
    for region in _sequence(target.get("memory")):
        item = _mapping(region)
        name = _text(item.get("name"))
        origin = _int(item.get("origin"))
        length = _int(item.get("length"))
        if name is not None and origin is not None and length is not None:
            memory.append((name, origin, length))
    return FirmwareView(
        target_id=target_id,
        mcu=mcu,
        core=_text(target.get("core")) or "unknown",
        framework=_text(target.get("framework")) or "other",
        elf_path=elf_artifact_path(target),
        memory=tuple(memory),
    )


def elf_artifact_path(target: Mapping[str, Any]) -> str | None:
    """Return the path of the first ELF artifact on a firmware target, if any."""
    for artifact in _sequence(target.get("artifacts")):
        item = _mapping(artifact)
        if _text(item.get("kind")) == "elf":
            return _text(item.get("path"))
    return None


def matrix_view(ir: Mapping[str, Any]) -> MatrixView | None:
    """Extract the keyboard matrix, if the IR has one."""
    matrix = _mapping(_mapping(ir.get("keyboard")).get("matrix"))
    rows = tuple(str(p) for p in _sequence(matrix.get("row_pins")) if isinstance(p, str))
    cols = tuple(str(p) for p in _sequence(matrix.get("col_pins")) if isinstance(p, str))
    if not rows and not cols:
        return None
    return MatrixView(
        rows=rows,
        cols=cols,
        diode_direction=_text(matrix.get("diode_direction")) or "unknown",
    )


def peripherals_view(ir: Mapping[str, Any]) -> tuple[PeripheralView, ...]:
    """Extract peripheral mappings, preserving IR order for deterministic output."""
    firmware = _mapping(ir.get("firmware"))
    out: list[PeripheralView] = []
    for periph in _sequence(firmware.get("peripherals")):
        item = _mapping(periph)
        signals = tuple(
            (str(_mapping(sig).get("name", "")), str(_mapping(sig).get("pin", "")))
            for sig in _sequence(item.get("signals"))
            if _mapping(sig).get("name") and _mapping(sig).get("pin")
        )
        out.append(
            PeripheralView(
                id=_text(item.get("id")) or "periph:unknown",
                kind=_text(item.get("kind")) or "other",
                base_address=_int(item.get("base_address")),
                signals=signals,
            )
        )
    return tuple(out)


def boot_markers(ir: Mapping[str, Any]) -> tuple[str, ...]:
    """Optional ``ext.renode.boot_markers`` override, else :data:`DEFAULT_BOOT_MARKERS`."""
    ext = _mapping(ir.get("ext"))
    renode = _mapping(ext.get("renode"))
    configured = renode.get("boot_markers")
    markers = tuple(m for m in _sequence(configured) if isinstance(m, str) and m)
    return markers or DEFAULT_BOOT_MARKERS


# ---------------------------------------------------------------------------
# Pin / platform helpers
# ---------------------------------------------------------------------------


def split_pin(pin: str) -> tuple[str, int] | None:
    """Split an STM32 pin name such as ``B12`` into ``("gpioPortB", 12)``."""
    if len(pin) < 2 or pin[0].upper() not in "ABCDEFGHIK":
        return None
    port = pin[0].upper()
    try:
        number = int(pin[1:])
    except ValueError:
        return None
    if not 0 <= number <= 15:
        return None
    return f"gpioPort{port}", number


def unsupported_mcu_reason(mcu: str) -> str | None:
    """Return a human reason when the MCU is outside the modelled set, else ``None``."""
    normalized = mcu.upper()
    if any(normalized.startswith(prefix) for prefix in SUPPORTED_MCU_PREFIXES):
        return None
    return (
        f"MCU {mcu!r} is not covered by the generated platform "
        f"({RENODE_BASE_PLATFORM}); supported prefixes: {', '.join(SUPPORTED_MCU_PREFIXES)}"
    )


def _ports_comment(matrix: MatrixView | None) -> list[str]:
    if matrix is None:
        return ["// keyboard matrix: not present in IR"]
    lines: list[str] = []
    for label, pins in (("rows", matrix.rows), ("cols", matrix.cols)):
        rendered: list[str] = []
        for pin in pins:
            resolved = split_pin(pin)
            if resolved is None:
                rendered.append(f"{pin} (unrecognised)")
            else:
                port, number = resolved
                rendered.append(f"{pin} ({port}#{number})")
        lines.append(f"//   {label}: {', '.join(rendered)}")
    lines.append(f"//   diode direction: {matrix.diode_direction}")
    return lines


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------


def generate_repl(ir: Mapping[str, Any]) -> str:
    """Return a deterministic Renode ``.repl`` platform description for the IR."""
    view = firmware_view(ir)
    reason = unsupported_mcu_reason(view.mcu)
    if reason is not None:
        raise DerivationError(reason)
    matrix = matrix_view(ir)
    peripherals = peripherals_view(ir)

    lines = [
        "// atomc generated Renode platform description -- do not edit by hand.",
        f"// firmware target: {view.target_id}",
        f"// mcu: {view.mcu} ({view.core}), framework: {view.framework}",
        f"// base platform: {RENODE_BASE_PLATFORM} (generic STM32F4 model)",
        "//",
        "// Keyboard GPIO expected by QMK/ChibiOS (matrix pin map from IR):",
    ]
    lines.extend(_ports_comment(matrix))
    lines.append("//")
    lines.append(
        "// Peripheral map from IR (addresses are informational; the base platform wires them):"
    )
    if peripherals:
        for periph in peripherals:
            address = f"0x{periph.base_address:08X}" if periph.base_address is not None else "n/a"
            signals = (
                " ".join(f"{name}={pin}" for name, pin in periph.signals)
                if periph.signals
                else "no named signals"
            )
            lines.append(f"//   {periph.id}: {periph.kind} @ {address} ({signals})")
    else:
        lines.append("//   none declared in IR")
    if view.memory:
        rendered = ", ".join(
            f"{name} origin=0x{origin:08X} length=0x{length:08X}"
            for name, origin, length in view.memory
        )
        lines.append(f"// memory (IR): {rendered}")
    lines.extend(["", f'using "{RENODE_BASE_PLATFORM}"', ""])
    return "\n".join(lines)


def generate_resc(
    ir: Mapping[str, Any],
    *,
    repl_path: str,
    elf_path: str,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> str:
    """Return a deterministic Renode ``.resc`` script that loads and starts the firmware.

    The script ends with ``start`` and intentionally has no ``quit``: the caller bounds the run
    with a subprocess timeout so partial output is still captured and analysed.
    """
    if timeout_s <= 0:
        raise DerivationError(f"timeout_s must be positive, got {timeout_s!r}")
    view = firmware_view(ir)
    name = view.target_id.removeprefix("fw:") or "firmware"
    lines = [
        f":name: {name} boot",
        f":description: generated from system_ir.json for {view.mcu}; bounded to {timeout_s:g}s",
        "",
        "using sysbus",
        f'$name?="{name}"',
        "mach create $name",
        f"machine LoadPlatformDescription @{repl_path}",
        f"$bin?=@{elf_path}",
        "sysbus LoadELF $bin",
        "",
        "start",
        "",
    ]
    return "\n".join(lines)


def generate_scripts(
    ir: Mapping[str, Any],
    *,
    repl_path: str,
    elf_path: str,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> GeneratedScripts:
    """Derive both script texts and the metadata the gates log as evidence."""
    return GeneratedScripts(
        repl=generate_repl(ir),
        resc=generate_resc(ir, repl_path=repl_path, elf_path=elf_path, timeout_s=timeout_s),
        target_id=firmware_view(ir).target_id,
        mcu=firmware_view(ir).mcu,
        matrix=matrix_view(ir),
        peripherals=peripherals_view(ir),
    )


__all__ = [
    "DEFAULT_BOOT_MARKERS",
    "DEFAULT_TIMEOUT_S",
    "RENODE_BASE_PLATFORM",
    "SUPPORTED_MCU_PREFIXES",
    "DerivationError",
    "FirmwareView",
    "GeneratedScripts",
    "MatrixView",
    "PeripheralView",
    "boot_markers",
    "elf_artifact_path",
    "firmware_view",
    "generate_repl",
    "generate_resc",
    "generate_scripts",
    "matrix_view",
    "peripherals_view",
    "split_pin",
    "unsupported_mcu_reason",
]
