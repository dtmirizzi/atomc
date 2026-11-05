"""Lazy import helpers: availability probing never imports the target module."""

from __future__ import annotations

from atomcd.kernels.importer import (
    import_module,
    module_available,
    module_version,
    probe_modules,
)


def test_module_available_for_stdlib() -> None:
    assert module_available("json") is True


def test_module_available_for_missing_module() -> None:
    assert module_available("atomc_definitely_missing_module") is False


def test_module_available_handles_missing_parent() -> None:
    assert module_available("atomc_definitely_missing.child") is False


def test_module_version_for_unknown_distribution() -> None:
    assert module_version("definitely-not-an-installed-distribution") is None


def test_import_module_returns_module() -> None:
    assert import_module("json").__name__ == "json"


def test_probe_modules_reports_missing() -> None:
    result = probe_modules("atomc_definitely_missing_module")
    assert result.available is False
    assert "missing" in result.detail


def test_probe_modules_reports_present() -> None:
    result = probe_modules("json")
    assert result.available is True
    assert result.detail == "installed"
