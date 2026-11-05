"""The OCP engine executes in a child process; its pure paths are unit-testable in-process."""

from __future__ import annotations

import os

import pytest
from atomcd.kernels.importer import module_available
from atomcd.kernels.ocp_engine import OcpEngine, make_engine


def test_make_engine_returns_engine() -> None:
    assert isinstance(make_engine(), OcpEngine)


def test_ping_reports_pid() -> None:
    engine = OcpEngine()
    assert engine.handle("ping", {}) == {"pong": True, "pid": os.getpid()}
    engine.close()


def test_version_does_not_require_engine_import() -> None:
    engine = OcpEngine()
    result = engine.handle("version", {})
    assert "build123d" in result
    assert "ocp" in result
    assert result["pid"] == os.getpid()
    engine.close()


def test_unknown_op_rejected() -> None:
    with pytest.raises(ValueError, match="unknown OCP op"):
        OcpEngine().handle("frobnicate", {})


def test_export_without_part_raises() -> None:
    engine = OcpEngine()
    with pytest.raises(RuntimeError, match="no part to export"):
        engine.handle("export_step", {"path": "/tmp/nope.step"})
    engine.close()


@pytest.mark.skipif(
    module_available("build123d"), reason="build123d installed: smoke covers this path"
)
def test_make_box_without_build123d_raises_import_error() -> None:
    with pytest.raises(ModuleNotFoundError):
        OcpEngine().handle("make_box", {"length": 1.0, "width": 1.0, "height": 1.0})
