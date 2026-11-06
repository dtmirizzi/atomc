"""Tests for the ``cad.generate`` tool, including the no-CAD unavailable path."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest
from atomc_plugin_cad_jig import plugin

plugin_module = importlib.import_module("atomc_plugin_cad_jig.plugin")


async def test_generate_reports_unavailable_without_build123d(
    ctx: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(plugin_module, "build123d_available", lambda: False)
    result = await plugin.generate(ctx, {"targets": ["plate"], "formats": ["step"]})
    assert result["status"] == "unavailable"
    assert result["reason"] == "build123d_missing"
    assert result["artifacts"] == []
    assert ctx.transactions == []


async def test_generate_defaults_report_unavailable(
    ctx: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(plugin_module, "build123d_available", lambda: False)
    result = await plugin.generate(ctx)
    assert result["status"] == "unavailable"
    assert result["targets"] == ["plate", "case", "jig"]
    assert result["formats"] == ["step", "stl"]


async def test_generate_records_artifacts_when_cad_present(
    ctx: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_build_and_export(
        models: Any,
        *,
        targets: list[str],
        formats: list[str],
        output_dir: Path,
    ) -> list[dict[str, Any]]:
        output_dir.mkdir(parents=True, exist_ok=True)
        descriptors: list[dict[str, Any]] = []
        for target in targets:
            for fmt in formats:
                path = output_dir / f"{target}.{fmt}"
                path.write_bytes(b"solid")
                descriptors.append(
                    {
                        "target": target,
                        "kind": fmt,
                        "path": path,
                        "bytes": path.stat().st_size,
                        "sha256": "sha256:" + "0" * 64,
                    }
                )
        return descriptors

    monkeypatch.setattr(plugin_module, "build123d_available", lambda: True)
    monkeypatch.setattr(plugin_module, "build_and_export", fake_build_and_export)

    result = await plugin.generate(ctx, {"targets": ["plate"], "formats": ["step", "stl"]})
    assert result["status"] == "ok"
    assert [a["kind"] for a in result["artifacts"]] == ["step", "stl"]
    assert result["artifacts"][0]["id"] == "art:cad-plate-step"
    assert result["artifacts"][0]["produced_by"] == "plugin:cad-jig@0.1.0"

    path, base_rev, ops = ctx.transactions[0]
    assert path == "/mechanical"
    assert base_rev == 7
    assert ops[0]["op"] == "replace"
    assert ops[0]["path"] == "/artifacts"
    recorded = ops[0]["value"]
    assert {item["kind"] for item in recorded} == {"step", "stl"}


async def test_generate_rejects_unknown_target(ctx: Any) -> None:
    with pytest.raises(ValueError, match="targets"):
        await plugin.generate(ctx, {"targets": ["nope"]})


async def test_generate_rejects_path_traversal(ctx: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plugin_module, "build123d_available", lambda: True)
    with pytest.raises(ValueError, match="output_dir"):
        await plugin.generate(ctx, {"output_dir": "../escape"})
