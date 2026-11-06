"""Tests for the CAD builder module's no-toolchain honesty path."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from atomc_plugin_cad_jig import cad
from atomc_plugin_cad_jig.models import derive_models


def test_builders_cover_all_targets() -> None:
    assert set(cad.BUILDERS) == {"plate", "case", "jig", "pcb"}


def test_build123d_available_is_boolean() -> None:
    assert isinstance(cad.build123d_available(), bool)


def test_sha256_helper(tmp_path: Path) -> None:
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"solid")
    assert cad._sha256(path) == f"sha256:{hashlib.sha256(b'solid').hexdigest()}"


def test_builders_raise_when_build123d_missing(
    atomc_pad_ir: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cad, "build123d_available", lambda: False)
    models = derive_models(atomc_pad_ir)
    for builder in cad.BUILDERS.values():
        with pytest.raises(cad.CadUnavailableError):
            builder(models)
    with pytest.raises(cad.CadUnavailableError):
        cad.build_and_export(
            models, targets=["plate"], formats=["step"], output_dir=tmp_path / "out"
        )
