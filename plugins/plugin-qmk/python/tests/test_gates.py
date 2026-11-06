from __future__ import annotations

import copy
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from atomc_plugin_qmk import gates as gate_impl
from atomc_plugin_qmk.derivation import derive
from atomc_plugin_qmk.gates import (
    ToolchainCheck,
    check_matrix_pins,
    check_toolchain,
    compile_gate,
    compile_qmk,
    compile_tool,
    generate_tool,
    matrix_pins_gate,
)


class FakeContext:
    def __init__(self, ir: dict[str, Any], artifact_root: Path, *, fail_transact: bool = False):
        self.ir = ir
        self.rev = 1
        self.artifact_root = artifact_root
        self.fail_transact = fail_transact
        self.transactions: list[tuple[str, int, list[dict[str, Any]]]] = []

    def _resolve(self, path: str) -> Any:
        if path in ("", "/"):
            return self.ir
        current: Any = self.ir
        for part in path.strip("/").split("/"):
            if not isinstance(current, dict) or part not in current:
                raise KeyError(f"pointer {path!r} not found")
            current = current[part]
        return current

    async def ir_read(self, path: str = "/") -> dict[str, Any]:
        value = self._resolve(path)
        if path in ("", "/"):
            return {"rev": self.rev, "value": value}
        rev = int(value.get("_meta", {}).get("rev", 0)) if isinstance(value, dict) else 0
        return {"rev": rev, "value": value}

    async def ir_transact(
        self, path: str, base_rev: int, ops: list[dict[str, Any]]
    ) -> SimpleNamespace:
        if self.fail_transact:
            raise RuntimeError("locked by another holder")
        self.transactions.append((path, base_rev, ops))
        self.rev += 1
        return SimpleNamespace(new_rev=self.rev, changed_paths=[path])


def _qmk_home(tmp_path: Path) -> Path:
    home = tmp_path / "qmk_firmware"
    (home / "keyboards").mkdir(parents=True)
    return home


def _ok_runner(artifact_name: str, content: bytes = b"firmware"):
    def runner(command: list[str], *, cwd: str, env: Any, timeout: int):
        build = Path(cwd) / ".build"
        build.mkdir(parents=True, exist_ok=True)
        (build / artifact_name).write_bytes(content)
        return subprocess.CompletedProcess(command, 0, "ok", "")

    return runner


def _fail_runner(stderr: str = "compiler exploded"):
    def runner(command: list[str], *, cwd: str, env: Any, timeout: int):
        return subprocess.CompletedProcess(command, 2, "", stderr)

    return runner


def test_check_matrix_pins_matches_fixture(example_ir: dict[str, Any]) -> None:
    ok, problems = check_matrix_pins(example_ir)
    assert ok
    assert problems == []


def test_check_matrix_pins_detects_mismatch(example_ir: dict[str, Any]) -> None:
    generated = derive(example_ir).keyboard_json_data
    generated = copy.deepcopy(generated)
    generated["matrix_pins"]["cols"] = ["A3", "A4", "A5"]
    ok, problems = check_matrix_pins(example_ir, generated)
    assert not ok
    assert "col pins" in problems[0]


def test_check_matrix_pins_missing_keyboard() -> None:
    ok, problems = check_matrix_pins({})
    assert not ok
    assert "no /keyboard" in problems[0]


def test_check_toolchain_skip_without_qmk(tmp_path: Path) -> None:
    check = check_toolchain(tmp_path / "qmk", which=lambda _: None)
    assert not check.available
    assert "not found on PATH" in str(check.summary)
    assert check.suggestions


def test_check_toolchain_skip_without_home(tmp_path: Path) -> None:
    check = check_toolchain(tmp_path / "missing", which=lambda _: "/usr/bin/qmk")
    assert not check.available
    assert "does not exist" in str(check.summary)


def test_compile_skip_without_qmk(tmp_path: Path, example_ir: dict[str, Any]) -> None:
    called = False

    def runner(command: list[str], **kwargs: Any):
        nonlocal called
        called = True
        raise AssertionError("runner must not be called")

    outcome = compile_qmk(
        example_ir,
        qmk_home=tmp_path,
        artifact_root=tmp_path / "art",
        which=lambda _: None,
        runner=runner,
    )
    assert outcome.status == "SKIP"
    assert "not found on PATH" in outcome.summary
    assert outcome.suggestions
    assert not called


def test_compile_skip_without_qmk_home(tmp_path: Path, example_ir: dict[str, Any]) -> None:
    outcome = compile_qmk(
        example_ir,
        qmk_home=tmp_path / "missing",
        artifact_root=tmp_path / "art",
        which=lambda _: "/usr/bin/qmk",
    )
    assert outcome.status == "SKIP"
    assert "QMK_HOME" in outcome.summary


def test_compile_fail_on_nonzero(tmp_path: Path, example_ir: dict[str, Any]) -> None:
    home = _qmk_home(tmp_path)
    outcome = compile_qmk(
        example_ir,
        qmk_home=home,
        artifact_root=tmp_path / "art",
        which=lambda _: "/usr/bin/qmk",
        runner=_fail_runner("boom"),
    )
    assert outcome.status == "FAIL"
    assert "exit code 2" in outcome.summary
    assert "boom" in str(outcome.evidence)
    assert outcome.returncode == 2


def test_compile_pass_records_artifact(tmp_path: Path, example_ir: dict[str, Any]) -> None:
    home = _qmk_home(tmp_path)
    outcome = compile_qmk(
        example_ir,
        qmk_home=home,
        artifact_root=tmp_path / "art",
        which=lambda _: "/usr/bin/qmk",
        runner=_ok_runner("atomc_pad_default.bin", b"payload"),
    )
    assert outcome.status == "PASS"
    assert outcome.artifact_path is not None
    assert outcome.artifact_path.is_file()
    assert outcome.artifact_path.read_bytes() == b"payload"
    assert outcome.artifact_sha256 is not None
    assert outcome.artifact_sha256.startswith("sha256:")
    assert outcome.artifact_id == "art:qmk_atomc_pad_default"
    assert outcome.artifact_bytes == len(b"payload")
    assert outcome.artifact_kind == "bin"


def test_compile_fail_when_artifact_missing(tmp_path: Path, example_ir: dict[str, Any]) -> None:
    home = _qmk_home(tmp_path)

    def runner(command: list[str], *, cwd: str, env: Any, timeout: int):
        return subprocess.CompletedProcess(command, 0, "ok", "")

    outcome = compile_qmk(
        example_ir,
        qmk_home=home,
        artifact_root=tmp_path / "art",
        which=lambda _: "/usr/bin/qmk",
        runner=runner,
    )
    assert outcome.status == "FAIL"
    assert "no fresh" in outcome.summary


def test_compile_fail_when_only_stale_artifact(tmp_path: Path, example_ir: dict[str, Any]) -> None:
    home = _qmk_home(tmp_path)
    build = home / ".build"
    build.mkdir()
    stale = build / "atomc_pad_default.bin"
    stale.write_bytes(b"old")
    os.utime(stale, (1, 1))

    def runner(command: list[str], *, cwd: str, env: Any, timeout: int):
        return subprocess.CompletedProcess(command, 0, "ok", "")

    outcome = compile_qmk(
        example_ir,
        qmk_home=home,
        artifact_root=tmp_path / "art",
        which=lambda _: "/usr/bin/qmk",
        runner=runner,
    )
    assert outcome.status == "FAIL"
    assert "no fresh" in outcome.summary


def test_compile_refuses_non_plugin_keyboard(tmp_path: Path, example_ir: dict[str, Any]) -> None:
    home = _qmk_home(tmp_path)
    real = home / "keyboards" / "atomc" / "pad"
    real.mkdir(parents=True)
    (real / "keyboard.json").write_text("{}", encoding="utf-8")

    def runner(command: list[str], **kwargs: Any):
        raise AssertionError("runner must not be called")

    outcome = compile_qmk(
        example_ir,
        qmk_home=home,
        artifact_root=tmp_path / "art",
        which=lambda _: "/usr/bin/qmk",
        runner=runner,
    )
    assert outcome.status == "FAIL"
    assert "refusing to replace non-plugin" in outcome.summary


def test_compile_replaces_plugin_managed_copy(tmp_path: Path, example_ir: dict[str, Any]) -> None:
    home = _qmk_home(tmp_path)
    managed = home / "keyboards" / "atomc" / "pad"
    managed.mkdir(parents=True)
    (managed / ".atomc-plugin-qmk").write_text("managed\n", encoding="utf-8")
    (managed / "stale.txt").write_text("old\n", encoding="utf-8")

    outcome = compile_qmk(
        example_ir,
        qmk_home=home,
        artifact_root=tmp_path / "art",
        which=lambda _: "/usr/bin/qmk",
        runner=_ok_runner("atomc_pad_default.bin", b"payload"),
    )
    assert outcome.status == "PASS"
    assert outcome.artifact_path is not None
    assert not (managed / "stale.txt").exists()
    assert (managed / ".atomc-plugin-qmk").is_file()


def test_compile_bounds_compiler_output(tmp_path: Path, example_ir: dict[str, Any]) -> None:
    home = _qmk_home(tmp_path)
    outcome = compile_qmk(
        example_ir,
        qmk_home=home,
        artifact_root=tmp_path / "art",
        which=lambda _: "/usr/bin/qmk",
        runner=_fail_runner("x" * 5000),
    )
    text = str(outcome.evidence[0]["message"])
    assert len(text) <= gate_impl._MAX_OUTPUT + 60
    assert text.startswith("...")


def test_compile_derivation_failure(tmp_path: Path) -> None:
    outcome = compile_qmk(
        {"meta": {"name": "empty"}},
        qmk_home=_qmk_home(tmp_path),
        artifact_root=tmp_path / "art",
        which=lambda _: "/usr/bin/qmk",
    )
    assert outcome.status == "FAIL"
    assert "derivation failed" in outcome.summary


@pytest.mark.asyncio
async def test_matrix_gate_pass(tmp_path: Path, example_ir: dict[str, Any]) -> None:
    result = await matrix_pins_gate(FakeContext(example_ir, tmp_path))
    assert result["status"] == "PASS"
    assert "match" in result["summary"]


@pytest.mark.asyncio
async def test_matrix_gate_fail_without_keyboard(tmp_path: Path) -> None:
    result = await matrix_pins_gate(FakeContext({"meta": {}}, tmp_path))
    assert result["status"] == "FAIL"


@pytest.mark.asyncio
async def test_compile_gate_skip_without_toolchain(
    tmp_path: Path, example_ir: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        gate_impl,
        "check_toolchain",
        lambda *args, **kwargs: ToolchainCheck(
            available=False,
            qmk_path=None,
            qmk_home=tmp_path,
            summary="qmk unavailable",
            evidence=[{"kind": "text", "message": "missing"}],
            suggestions=[{"message": "install qmk"}],
        ),
    )
    result = await compile_gate(FakeContext(example_ir, tmp_path))
    assert result["status"] == "SKIP"
    assert result["suggestions"]


@pytest.mark.asyncio
async def test_compile_gate_pass_writes_firmware(
    tmp_path: Path, example_ir: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _qmk_home(tmp_path)
    monkeypatch.setattr(
        gate_impl,
        "check_toolchain",
        lambda *args, **kwargs: ToolchainCheck(
            available=True, qmk_path="/usr/bin/qmk", qmk_home=home
        ),
    )
    monkeypatch.setattr(
        gate_impl,
        "run_qmk_compile",
        _ok_runner("atomc_pad_default.bin", b"firmware"),
    )
    ctx = FakeContext(example_ir, tmp_path / "art")
    result = await compile_gate(ctx)
    assert result["status"] == "PASS"
    assert result["evidence"]
    assert len(ctx.transactions) == 1
    path, base_rev, ops = ctx.transactions[0]
    assert path == "/firmware"
    assert base_rev == example_ir["firmware"]["_meta"]["rev"]
    assert ops[0]["op"] == "add"
    assert ops[0]["path"] == "/targets/0/artifacts"


@pytest.mark.asyncio
async def test_compile_gate_creates_firmware_node_when_absent(
    tmp_path: Path, example_ir: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _qmk_home(tmp_path)
    monkeypatch.setattr(
        gate_impl,
        "check_toolchain",
        lambda *args, **kwargs: ToolchainCheck(
            available=True, qmk_path="/usr/bin/qmk", qmk_home=home
        ),
    )
    monkeypatch.setattr(
        gate_impl,
        "run_qmk_compile",
        _ok_runner("atomc_pad_default.bin", b"firmware"),
    )
    ir = copy.deepcopy(example_ir)
    ir.pop("firmware")
    ctx = FakeContext(ir, tmp_path / "art")
    result = await compile_gate(ctx)
    assert result["status"] == "PASS"
    path, base_rev, ops = ctx.transactions[0]
    assert path == "/firmware"
    assert base_rev == 0
    assert ops[0]["op"] == "add"
    assert ops[0]["path"] == ""


@pytest.mark.asyncio
async def test_compile_gate_fail_when_firmware_write_fails(
    tmp_path: Path, example_ir: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _qmk_home(tmp_path)
    monkeypatch.setattr(
        gate_impl,
        "check_toolchain",
        lambda *args, **kwargs: ToolchainCheck(
            available=True, qmk_path="/usr/bin/qmk", qmk_home=home
        ),
    )
    monkeypatch.setattr(
        gate_impl,
        "run_qmk_compile",
        _ok_runner("atomc_pad_default.bin", b"firmware"),
    )
    result = await compile_gate(FakeContext(example_ir, tmp_path / "art", fail_transact=True))
    assert result["status"] == "FAIL"
    assert "recording /firmware failed" in result["summary"]


@pytest.mark.asyncio
async def test_compile_gate_fail_without_keyboard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _qmk_home(tmp_path)
    monkeypatch.setattr(
        gate_impl,
        "check_toolchain",
        lambda *args, **kwargs: ToolchainCheck(
            available=True, qmk_path="/usr/bin/qmk", qmk_home=home
        ),
    )
    result = await compile_gate(FakeContext({"meta": {}}, tmp_path / "art"))
    assert result["status"] == "FAIL"


@pytest.mark.asyncio
async def test_generate_tool(tmp_path: Path, example_ir: dict[str, Any]) -> None:
    result = await generate_tool(FakeContext(example_ir, tmp_path / "art"), {})
    assert result["status"] == "PASS"
    assert result["matrix_pins_match_ir"] is True
    assert set(result["files"]) == {
        "keyboards/atomc/pad/keyboard.json",
        "keyboards/atomc/pad/keymaps/default/keymap.c",
    }
    for path in result["files"].values():
        assert Path(path).is_file()


@pytest.mark.asyncio
async def test_compile_tool_pass(
    tmp_path: Path, example_ir: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _qmk_home(tmp_path)
    monkeypatch.setattr(
        gate_impl,
        "check_toolchain",
        lambda *args, **kwargs: ToolchainCheck(
            available=True, qmk_path="/usr/bin/qmk", qmk_home=home
        ),
    )
    monkeypatch.setattr(
        gate_impl,
        "run_qmk_compile",
        _ok_runner("atomc_pad_default.bin", b"firmware"),
    )
    ctx = FakeContext(example_ir, tmp_path / "art")
    result = await compile_tool(ctx, {})
    assert result["status"] == "PASS"
    assert "artifact" in result
    assert len(ctx.transactions) == 1


def test_compile_skips_when_ir_missing_keyboard(tmp_path: Path) -> None:
    outcome = compile_qmk(
        {"meta": {"name": "empty"}},
        qmk_home=_qmk_home(tmp_path),
        artifact_root=tmp_path / "art",
        which=lambda _: "/usr/bin/qmk",
    )
    assert outcome.status == "FAIL"
