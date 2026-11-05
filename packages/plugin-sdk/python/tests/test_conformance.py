"""Conformance checks for full plugin implementations.

Each test builds a fresh implementation class so decorating one does not leak
``__atomc_handlers__``/``__atomc_manifest__`` into another.
"""

from __future__ import annotations

from typing import Any

import pytest
from atomc_plugin_sdk.conformance import assert_conformance, conformance
from atomc_plugin_sdk.errors import PluginConformanceError
from atomc_plugin_sdk.plugin import atomc_plugin, define_plugin


def _good_class() -> type:
    class Good:
        def check_all_in_stock(self, ctx: Any) -> None:
            pass

        def search_parts(self, ctx: Any) -> None:
            pass

        def quote(self, ctx: Any) -> None:
            pass

    return Good


def _good_plugin(valid_manifest: dict[str, Any], **kwargs: Any) -> Any:
    return atomc_plugin(manifest=valid_manifest, **kwargs)(_good_class())


def test_valid_plugin_passes(valid_manifest: dict[str, Any]) -> None:
    report = conformance(_good_plugin(valid_manifest))
    assert report.ok
    assert report.findings == ()
    assert report.plugin_name == "sourcing"


def test_valid_plugin_instance_passes(valid_manifest: dict[str, Any]) -> None:
    report = conformance(_good_plugin(valid_manifest)())
    assert report.ok


def test_missing_handler(valid_manifest: dict[str, Any]) -> None:
    class Partial:
        def check_all_in_stock(self, ctx: Any) -> None:
            pass

    plugin = atomc_plugin(manifest=valid_manifest)(Partial)
    report = conformance(plugin)
    assert not report.ok
    codes = {f.code for f in report.findings}
    assert "MISSING_HANDLER" in codes
    assert any(f.path == "/handlers/search_parts" for f in report.findings)


def test_non_callable_handler(valid_manifest: dict[str, Any]) -> None:
    class Weird:
        search_parts = 42  # not callable

        def check_all_in_stock(self, ctx: Any) -> None:
            pass

        def quote(self, ctx: Any) -> None:
            pass

    plugin = atomc_plugin(manifest=valid_manifest)(Weird)
    report = conformance(plugin)
    assert "HANDLER_NOT_CALLABLE" in {f.code for f in report.findings}


def test_undeclared_handler_rejected(valid_manifest: dict[str, Any]) -> None:
    handlers = {
        "check_all_in_stock": lambda ctx: None,
        "search_parts": lambda ctx: None,
        "quote": lambda ctx: None,
        "sneaky_extra": lambda ctx: None,
    }
    plugin = atomc_plugin(manifest=valid_manifest, handlers=handlers)(_good_class())
    report = conformance(plugin)
    assert not report.ok
    assert "UNDECLARED_HANDLER" in {f.code for f in report.findings}


def test_explicit_handler_registry_complete(valid_manifest: dict[str, Any]) -> None:
    handlers = {
        "check_all_in_stock": lambda ctx: None,
        "search_parts": lambda ctx: None,
        "quote": lambda ctx: None,
    }
    definition = define_plugin(valid_manifest, handlers=handlers)
    assert conformance(definition).ok


def test_registry_missing_handler(valid_manifest: dict[str, Any]) -> None:
    definition = define_plugin(valid_manifest, handlers={"quote": lambda ctx: None})
    report = conformance(definition)
    assert "MISSING_HANDLER" in {f.code for f in report.findings}


def test_factory_error(valid_manifest: dict[str, Any]) -> None:
    @atomc_plugin(manifest=valid_manifest)
    def factory() -> Any:
        raise RuntimeError("boom")

    report = conformance(factory)
    assert not report.ok
    assert "FACTORY_ERROR" in {f.code for f in report.findings}


def test_factory_success(valid_manifest: dict[str, Any]) -> None:
    @atomc_plugin(manifest=valid_manifest)
    def factory() -> Any:
        return _good_class()()

    assert conformance(factory).ok


def test_instance_plugin(valid_manifest: dict[str, Any]) -> None:
    instance = _good_class()()
    plugin = atomc_plugin(manifest=valid_manifest)(instance)
    assert conformance(plugin).ok


def test_no_manifest_is_a_finding() -> None:
    report = conformance(object())
    assert not report.ok
    assert report.findings[0].code == "NO_MANIFEST"


def test_invalid_manifest_is_reported(valid_manifest: dict[str, Any]) -> None:
    valid_manifest["produces"] = ["/meta"]

    # Build directly to bypass the decorator's eager validation.
    class Raw:
        __atomc_manifest__ = valid_manifest

        def check_all_in_stock(self, ctx: Any) -> None: ...
        def search_parts(self, ctx: Any) -> None: ...
        def quote(self, ctx: Any) -> None: ...

    report = conformance(Raw)
    assert not report.ok
    assert "MANIFEST_INVALID" in {f.code for f in report.findings}


def test_mutating_tool_without_produces_invalid(valid_manifest: dict[str, Any]) -> None:
    valid_manifest["produces"] = []
    valid_manifest["tools"][0]["mutates"] = True

    class Raw:
        __atomc_manifest__ = valid_manifest

        def check_all_in_stock(self, ctx: Any) -> None: ...
        def search_parts(self, ctx: Any) -> None: ...
        def quote(self, ctx: Any) -> None: ...

    report = conformance(Raw)
    assert "MANIFEST_INVALID" in {f.code for f in report.findings}


def test_assert_conformance_returns_manifest(valid_manifest: dict[str, Any]) -> None:
    manifest = assert_conformance(_good_plugin(valid_manifest))
    assert manifest.name == "sourcing"


def test_assert_conformance_raises(valid_manifest: dict[str, Any]) -> None:
    class Partial:
        pass

    plugin = atomc_plugin(manifest=valid_manifest)(Partial)
    with pytest.raises(PluginConformanceError) as excinfo:
        assert_conformance(plugin)
    assert excinfo.value.plugin_name == "sourcing"
    assert excinfo.value.findings


def test_conformance_report_partitions_findings(valid_manifest: dict[str, Any]) -> None:
    definition = define_plugin(valid_manifest, handlers={"quote": lambda ctx: None})
    report = conformance(definition)
    assert report.errors == report.findings
    assert report.warnings == ()
