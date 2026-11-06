"""Plugin-level tests: conformance, manifest parity, gates and the generate tool."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from atomc_plugin_renode import (
    MANIFEST,
    MATRIX_SCAN_SKIP_REASON,
    RenodePlugin,
    manifest_path,
)
from atomc_plugin_renode.runner import RenodeRunResult
from atomc_plugin_sdk import conformance, load_manifest


def _ok_run(stdout: str = "", *, timed_out: bool = False) -> RenodeRunResult:
    return RenodeRunResult(
        exit_code=0, stdout=stdout, stderr="", timed_out=timed_out, duration_ms=5
    )


def test_plugin_passes_conformance() -> None:
    report = conformance(RenodePlugin())
    assert report.ok, [str(f) for f in report.errors]


def test_manifest_file_matches_code() -> None:
    on_disk = json.loads(Path(manifest_path()).read_text(encoding="utf-8"))
    assert on_disk == MANIFEST


def test_manifest_is_valid_and_declares_expected_surface() -> None:
    manifest = load_manifest(MANIFEST)
    assert manifest.plugin_id == "plugin:renode"
    assert [g.id for g in manifest.gates] == ["gate:fw.renode_boot", "gate:fw.matrix_scan"]
    assert [t.name for t in manifest.tools] == ["renode_generate"]
    assert manifest.produces == ["/simulation"]
    assert [w.id for w in manifest.watches] == ["renode:generate"]


def test_class_exposes_manifest_and_node_handler() -> None:
    assert RenodePlugin.__atomc_manifest__.name == "renode"
    instance = RenodePlugin()
    assert "renode:generate" in instance.__atomc_node_handlers__


async def test_boot_skips_without_binary(fake_ctx: Any) -> None:
    plugin = RenodePlugin(binary_resolver=lambda: None)
    result = await plugin.renode_boot(fake_ctx)
    assert result["status"] == "SKIP"
    assert "renode binary" in result["summary"]


async def test_boot_skips_without_elf(fake_ctx: Any, fixture_doc: dict[str, Any]) -> None:
    fixture_doc["firmware"]["targets"][0]["artifacts"] = []
    plugin = RenodePlugin(binary_resolver=lambda: "/opt/renode")
    result = await plugin.renode_boot(fake_ctx)
    assert result["status"] == "SKIP"
    assert "ELF" in result["summary"]


async def test_boot_skips_unsupported_mcu(fake_ctx: Any, fixture_doc: dict[str, Any]) -> None:
    fixture_doc["firmware"]["targets"][0]["mcu"] = "RP2040"
    plugin = RenodePlugin(binary_resolver=lambda: "/opt/renode")
    result = await plugin.renode_boot(fake_ctx)
    assert result["status"] == "SKIP"


async def test_boot_passes_with_banner(fake_ctx: Any, make_runner: Any) -> None:
    runner = make_runner(_ok_run("boot ... ATOMC-PAD READY\n"))
    plugin = RenodePlugin(runner=runner, binary_resolver=lambda: "/opt/renode")
    result = await plugin.renode_boot(fake_ctx)
    assert result["status"] == "PASS"
    assert result["refs"] == ["fw:main"]
    assert runner.calls
    assert runner.calls[0][0][0] == "/opt/renode"
    # The scripts were written into the artifact root.
    assert (fake_ctx.artifact_root / "atomc-pad.repl").is_file()
    assert (fake_ctx.artifact_root / "atomc-pad.resc").is_file()


async def test_boot_fails_on_hardfault(fake_ctx: Any, make_runner: Any) -> None:
    runner = make_runner(_ok_run("[ERROR] HardFault exception\n"))
    plugin = RenodePlugin(runner=runner, binary_resolver=lambda: "/opt/renode")
    result = await plugin.renode_boot(fake_ctx)
    assert result["status"] == "FAIL"
    assert any(step["kind"] == "text" for step in result["evidence"])


async def test_boot_fails_on_timeout_without_banner(fake_ctx: Any, make_runner: Any) -> None:
    runner = make_runner(_ok_run("starting\n", timed_out=True))
    plugin = RenodePlugin(runner=runner, binary_resolver=lambda: "/opt/renode")
    result = await plugin.renode_boot(fake_ctx)
    assert result["status"] == "FAIL"
    assert "timeout" in result["summary"]


async def test_matrix_scan_is_always_skip(fake_ctx: Any) -> None:
    plugin = RenodePlugin()
    result = await plugin.matrix_scan(fake_ctx)
    assert result["status"] == "SKIP"
    assert result["summary"] == MATRIX_SCAN_SKIP_REASON
    assert result["refs"] == ["fw:main"]


async def test_generate_writes_scripts_and_records_ir(
    fake_ctx: Any,
) -> None:
    plugin = RenodePlugin()
    outcome = await plugin.generate(fake_ctx, {"timeout_s": 1})
    assert outcome["result"]["recorded_in_ir"] is True
    artifact_root = fake_ctx.artifact_root
    assert (artifact_root / "atomc-pad.repl").is_file()
    assert (artifact_root / "atomc-pad.resc").is_file()
    assert fake_ctx.transactions
    path, _base_rev, ops = fake_ctx.transactions[0]
    assert path == "/simulation"
    assert any(op["path"] == "/platform/repl_path" for op in ops)


async def test_generate_node_handler(fake_ctx: Any) -> None:
    plugin = RenodePlugin()
    outcome = await plugin.generate_node(fake_ctx)
    assert "repl_path" in outcome["result"]


async def test_generate_adds_platform_when_absent(
    fake_ctx: Any, fixture_doc: dict[str, Any]
) -> None:
    del fixture_doc["simulation"]["platform"]
    fake_ctx._ir = fixture_doc
    plugin = RenodePlugin()
    outcome = await plugin.generate(fake_ctx, {})
    assert outcome["result"]["recorded_in_ir"] is True
    _path, _rev, ops = fake_ctx.transactions[0]
    assert ops[0]["op"] == "add"
    assert ops[0]["path"] == "/platform"


async def test_generate_records_relative_paths(fake_ctx: Any) -> None:
    plugin = RenodePlugin()
    outcome = await plugin.generate(fake_ctx, {})
    assert not outcome["result"]["repl_path"].startswith("/")
    assert outcome["result"]["repl_path"].endswith("atomc-pad.repl")


async def test_generate_derivation_error_propagates(fake_ctx: Any) -> None:
    import pytest
    from atomc_plugin_renode.derive import DerivationError

    broken = copy.deepcopy(fake_ctx._ir)
    broken["firmware"]["targets"][0]["artifacts"] = []
    fake_ctx._ir = broken
    plugin = RenodePlugin()
    with pytest.raises(DerivationError):
        await plugin.generate(fake_ctx, {})
