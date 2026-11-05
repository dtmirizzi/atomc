"""Decorator, factory and protocol behaviour without import-time side effects."""

from __future__ import annotations

from typing import Any

import pytest
from atomc_plugin_sdk.errors import ManifestValidationError
from atomc_plugin_sdk.manifest import PluginManifest, validate_manifest
from atomc_plugin_sdk.plugin import (
    HANDLERS_ATTR,
    MANIFEST_ATTR,
    AtomcPlugin,
    PluginDefinition,
    atomc_plugin,
    define_plugin,
    get_handlers,
    get_manifest,
)


class _Impl:
    def check_all_in_stock(self, ctx: Any) -> None:
        pass

    def search_parts(self, ctx: Any) -> None:
        pass

    def quote(self, ctx: Any) -> None:
        pass


def test_decorator_attaches_manifest_to_class(valid_manifest: dict[str, Any]) -> None:
    decorated = atomc_plugin(manifest=valid_manifest)(_Impl)
    assert get_manifest(decorated) is not None
    assert getattr(decorated, MANIFEST_ATTR).name == "sourcing"
    assert decorated is _Impl


def test_decorator_accepts_positional_manifest(valid_manifest: dict[str, Any]) -> None:
    decorated = atomc_plugin(valid_manifest)(_Impl)
    assert get_manifest(decorated).name == "sourcing"


def test_decorator_on_factory_function(valid_manifest: dict[str, Any]) -> None:
    @atomc_plugin(manifest=valid_manifest)
    def factory() -> _Impl:
        return _Impl()

    assert get_manifest(factory).name == "sourcing"
    assert isinstance(factory(), _Impl)


def test_factory_not_called_at_decoration_time(valid_manifest: dict[str, Any]) -> None:
    calls = 0

    @atomc_plugin(manifest=valid_manifest)
    def factory() -> _Impl:
        nonlocal calls
        calls += 1
        return _Impl()

    assert calls == 0
    factory()
    assert calls == 1


def test_decorator_on_instance(valid_manifest: dict[str, Any]) -> None:
    instance = _Impl()
    decorated = atomc_plugin(manifest=valid_manifest)(instance)
    assert decorated is instance
    assert get_manifest(decorated).name == "sourcing"


def test_decorator_validates_eagerly(valid_manifest: dict[str, Any]) -> None:
    valid_manifest["version"] = "not-semver"
    with pytest.raises(ManifestValidationError):
        atomc_plugin(manifest=valid_manifest)(_Impl)


def test_decorator_accepts_plugin_manifest_instance(valid_manifest: dict[str, Any]) -> None:
    manifest = validate_manifest(valid_manifest)
    decorated = atomc_plugin(manifest=manifest)(_Impl)
    assert get_manifest(decorated) is manifest


def test_handlers_registry_attached(valid_manifest: dict[str, Any]) -> None:
    class WithHandlers(_Impl):
        pass

    handlers = {"check_all_in_stock": _Impl.check_all_in_stock}
    decorated = atomc_plugin(manifest=valid_manifest, handlers=handlers)(WithHandlers)
    assert get_handlers(decorated) == handlers
    assert getattr(decorated, HANDLERS_ATTR) is not handlers


def test_slotted_instance_rejected(valid_manifest: dict[str, Any]) -> None:
    class Slotted:
        __slots__ = ()

    with pytest.raises(TypeError):
        atomc_plugin(manifest=valid_manifest)(Slotted())


def test_define_plugin_returns_immutable_definition(valid_manifest: dict[str, Any]) -> None:
    handlers = {
        "check_all_in_stock": _Impl.check_all_in_stock,
        "search_parts": _Impl.search_parts,
        "quote": _Impl.quote,
    }
    definition = define_plugin(valid_manifest, handlers=handlers)
    assert isinstance(definition, PluginDefinition)
    assert definition.manifest.name == "sourcing"
    assert definition.resolve("quote") is _Impl.quote
    assert definition.resolve("missing") is None
    with pytest.raises(TypeError):
        definition.handlers["new"] = lambda: None  # type: ignore[index]


def test_plugin_definition_callable_as_decorator(valid_manifest: dict[str, Any]) -> None:
    definition = define_plugin(valid_manifest)
    decorated = definition(_Impl)
    assert get_manifest(decorated) is definition.manifest


def test_manifest_attribute_is_plugin_manifest(valid_manifest: dict[str, Any]) -> None:
    decorated = atomc_plugin(manifest=valid_manifest)(_Impl)
    assert isinstance(get_manifest(decorated), PluginManifest)


def test_atomc_plugin_protocol_runtime_check(valid_manifest: dict[str, Any]) -> None:
    decorated = atomc_plugin(manifest=valid_manifest)(_Impl)
    assert isinstance(decorated(), AtomcPlugin)


def test_no_manifest_returns_none() -> None:
    assert get_manifest(object()) is None
    assert get_handlers(object()) is None
