"""Derivation tests: golden scripts, determinism and edge cases."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from atomc_plugin_renode.derive import (
    DEFAULT_BOOT_MARKERS,
    DerivationError,
    boot_markers,
    firmware_view,
    generate_repl,
    generate_resc,
    generate_scripts,
    matrix_view,
    peripherals_view,
    split_pin,
    unsupported_mcu_reason,
)


def test_repl_matches_golden(fixture_doc: dict[str, Any], goldens: Path) -> None:
    expected = (goldens / "atomc_pad.repl").read_text(encoding="utf-8")
    assert generate_repl(fixture_doc) == expected


def test_resc_matches_golden(fixture_doc: dict[str, Any], goldens: Path) -> None:
    expected = (goldens / "atomc_pad.resc").read_text(encoding="utf-8")
    generated = generate_resc(
        fixture_doc,
        repl_path="build/atomc-pad.repl",
        elf_path="build/atomc-pad.elf",
        timeout_s=5,
    )
    assert generated == expected


def test_generation_is_byte_deterministic(fixture_doc: dict[str, Any]) -> None:
    first = generate_scripts(fixture_doc, repl_path="a.repl", elf_path="b.elf", timeout_s=3)
    second = generate_scripts(fixture_doc, repl_path="a.repl", elf_path="b.elf", timeout_s=3)
    assert first == second
    assert first.repl == generate_repl(fixture_doc)


def test_generated_output_changes_with_ir(fixture_doc: dict[str, Any]) -> None:
    changed = copy.deepcopy(fixture_doc)
    changed["keyboard"]["matrix"]["row_pins"][0] = "C0"
    assert generate_repl(changed) != generate_repl(fixture_doc)


def test_repl_requires_a_firmware_target() -> None:
    with pytest.raises(DerivationError):
        generate_repl({})


def test_repl_rejects_unsupported_mcu(fixture_doc: dict[str, Any]) -> None:
    changed = copy.deepcopy(fixture_doc)
    changed["firmware"]["targets"][0]["mcu"] = "RP2040"
    with pytest.raises(DerivationError):
        generate_repl(changed)


def test_resc_rejects_non_positive_timeout(fixture_doc: dict[str, Any]) -> None:
    with pytest.raises(DerivationError):
        generate_resc(fixture_doc, repl_path="a", elf_path="b", timeout_s=0)


def test_firmware_view_extracts_elf_and_memory(fixture_doc: dict[str, Any]) -> None:
    view = firmware_view(fixture_doc)
    assert view.target_id == "fw:main"
    assert view.mcu == "STM32F411CEU6"
    assert view.elf_path == "build/atomc-pad.elf"
    assert ("flash", 134217728, 524288) in view.memory


def test_matrix_and_peripherals_views(fixture_doc: dict[str, Any]) -> None:
    matrix = matrix_view(fixture_doc)
    assert matrix is not None
    assert matrix.rows == ("B12", "B13", "B14")
    assert matrix.diode_direction == "COL2ROW"
    periphs = peripherals_view(fixture_doc)
    assert [p.id for p in periphs] == ["periph:usart1", "periph:gpioa"]
    assert periphs[0].signals == (("TX", "A9"), ("RX", "A10"))


def test_matrix_view_absent() -> None:
    assert matrix_view({}) is None


def test_split_pin() -> None:
    assert split_pin("B12") == ("gpioPortB", 12)
    assert split_pin("a0") == ("gpioPortA", 0)
    assert split_pin("P12") is None
    assert split_pin("B99") is None
    assert split_pin("") is None


def test_unsupported_mcu_reason() -> None:
    assert unsupported_mcu_reason("STM32F411CEU6") is None
    assert unsupported_mcu_reason("STM32F429ZI") is not None


def test_boot_markers_default_and_override(fixture_doc: dict[str, Any]) -> None:
    assert boot_markers({}) == DEFAULT_BOOT_MARKERS
    assert boot_markers(fixture_doc) == ("ATOMC-PAD READY",)
    assert boot_markers({"ext": {"renode": {"boot_markers": []}}}) == DEFAULT_BOOT_MARKERS


def test_generate_scripts_metadata(fixture_doc: dict[str, Any]) -> None:
    scripts = generate_scripts(fixture_doc, repl_path="r.repl", elf_path="f.elf", timeout_s=2)
    assert scripts.target_id == "fw:main"
    assert scripts.mcu == "STM32F411CEU6"
    assert scripts.matrix is not None
    assert len(scripts.peripherals) == 2


def test_repl_uses_renode_comment_syntax(fixture_doc: dict[str, Any]) -> None:
    # Renode .repl files use '//' comments; '#' lines break platform loading.
    repl = generate_repl(fixture_doc)
    assert not any(line.startswith("#") for line in repl.splitlines())


def test_resc_has_no_hash_comments(fixture_doc: dict[str, Any]) -> None:
    resc = generate_resc(fixture_doc, repl_path="r", elf_path="f")
    assert not any(line.startswith("#") for line in resc.splitlines())


def test_golden_files_are_repo_relative(goldens: Path) -> None:
    # The goldens must not embed machine-specific absolute paths.
    text = (goldens / "atomc_pad.resc").read_text(encoding="utf-8")
    assert str(Path.home()) not in text
