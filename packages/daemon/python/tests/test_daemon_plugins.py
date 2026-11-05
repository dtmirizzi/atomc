"""Manifest validation, discovery, registry conflicts, tools and scope enforcement."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from atomcd.errors import PluginFailureError
from atomcd.events import EventBus
from atomcd.ir_store import IRStore
from atomcd.plugins.context import ScopeError, pointer_allowed
from atomcd.plugins.discovery import build_registry, discover_from_project, load_plugin
from atomcd.plugins.manifest import Manifest, ManifestError, load_manifest, validate_manifest
from atomcd.plugins.registry import PluginRegistry
from atomcd.testing import make_manifest, make_plugin, manifest_dict


def store_for(root: Path) -> IRStore:
    store = IRStore(root)
    store.load()
    return store


# --- manifest validation -----------------------------------------------------


def test_valid_manifest_minimal() -> None:
    manifest = validate_manifest(
        manifest_dict(name="demo", watches=[{"id": "demo:w", "ir": ["/electrical"]}])
    )
    assert manifest.name == "demo"
    assert manifest.runtime.python == "fake:plugin"


@pytest.mark.parametrize(
    "mutation",
    [
        {"name": "Bad Name"},
        {"version": "one"},
        {"runtime": {}},
        {"watches": [{"id": "a", "ir": ["electrical"]}]},
        {"produces": ["/meta"]},
        {"produces": ["/nope"]},
        {"watches": [{"id": "a", "ir": ["/x"]}, {"id": "a", "ir": ["/y"]}]},
        {
            "tools": [
                {
                    "name": "t",
                    "description": "d",
                    "input_schema": {},
                    "agents": [],
                    "mutates": True,
                    "handler": "h",
                }
            ],
        },
    ],
)
def test_invalid_manifests_rejected(mutation: dict[str, Any]) -> None:
    data = manifest_dict()
    data.update(mutation)
    with pytest.raises(ManifestError):
        validate_manifest(data)


def test_rejects_unknown_keys() -> None:
    data = manifest_dict()
    data["extra"] = 1
    with pytest.raises(ManifestError):
        validate_manifest(data)


def test_manifest_version_mismatch() -> None:
    data = manifest_dict()
    data["manifest_version"] = "9.9.9"
    with pytest.raises(ManifestError):
        validate_manifest(data)


def _inject_fake_sdk(monkeypatch: pytest.MonkeyPatch, validate: Any) -> None:
    """Install a fake ``atomc_plugin_sdk`` module for the duration of a test."""
    import sys
    import types

    module = types.ModuleType("atomc_plugin_sdk")
    module.__dict__["validate_manifest"] = validate
    monkeypatch.setitem(sys.modules, "atomc_plugin_sdk", module)


def test_validate_manifest_consumes_sdk_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the SDK is installed, its foreign ``PluginManifest`` must be coerced, not rejected."""
    from pydantic import BaseModel, ConfigDict

    class SDKPluginManifest(BaseModel):
        model_config = ConfigDict(extra="allow")

    captured: dict[str, Any] = {}

    def sdk_validate(data: dict[str, Any]) -> SDKPluginManifest:
        captured.update(data)
        return SDKPluginManifest(**data)

    _inject_fake_sdk(monkeypatch, sdk_validate)
    result = validate_manifest(manifest_dict(name="sdk-demo"))
    assert isinstance(result, Manifest)
    assert result.name == "sdk-demo"
    assert captured["name"] == "sdk-demo"


def test_validate_manifest_translates_sdk_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A custom SDK validation exception is normalised to :class:`ManifestError`."""

    class SDKError(Exception):
        pass

    def sdk_validate(data: dict[str, Any]) -> Any:
        raise SDKError("bad manifest")

    _inject_fake_sdk(monkeypatch, sdk_validate)
    with pytest.raises(ManifestError, match="rejected by SDK"):
        validate_manifest(manifest_dict(name="broken"))


def test_validate_manifest_translates_sdk_issues(monkeypatch: pytest.MonkeyPatch) -> None:
    """An SDK result carrying issues (instead of raising) is normalised too."""

    class SDKResult:
        def __init__(self) -> None:
            self.issues = ["name must be kebab-case"]

    def sdk_validate(data: dict[str, Any]) -> SDKResult:
        return SDKResult()

    _inject_fake_sdk(monkeypatch, sdk_validate)
    with pytest.raises(ManifestError, match="rejected"):
        validate_manifest(manifest_dict(name="broken"))


def test_validate_manifest_with_real_sdk_if_installed() -> None:
    """Regression: with the real SDK installed, a valid manifest still yields a local Manifest."""
    pytest.importorskip("atomc_plugin_sdk")
    result = validate_manifest(
        manifest_dict(name="real-sdk", watches=[{"id": "real-sdk:w", "ir": ["/electrical"]}])
    )
    assert isinstance(result, Manifest)
    assert result.name == "real-sdk"


def test_invalid_manifest_with_real_sdk_if_installed() -> None:
    """Regression: the real SDK rejecting a manifest surfaces as :class:`ManifestError`."""
    pytest.importorskip("atomc_plugin_sdk")
    data = manifest_dict()
    data["name"] = "Bad Name"
    with pytest.raises(ManifestError):
        validate_manifest(data)


def test_pointer_allowed_boundaries() -> None:
    assert pointer_allowed(["/sourcing"], "/sourcing")
    assert pointer_allowed(["/sourcing"], "/sourcing/bom")
    assert not pointer_allowed(["/sourcing"], "/sourcing2")
    assert not pointer_allowed(["/sourcing"], "/electrical")


# --- discovery ---------------------------------------------------------------


def test_load_manifest_file(tmp_path: Path) -> None:
    path = tmp_path / "atomc-plugin.json"
    path.write_text(json.dumps(manifest_dict(name="onfile")), encoding="utf-8")
    assert load_manifest(path).name == "onfile"


def test_discover_loads_python_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    impl = tmp_path / "fake_plugin_impl.py"
    impl.write_text(
        "class Plugin:\n"
        "    def gate_ok(self, ctx):\n"
        "        return {'status': 'PASS', 'summary': 'ok'}\n"
        "plugin = Plugin()\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    plugin_dir = tmp_path / "plugins" / "demo"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "atomc-plugin.json").write_text(
        json.dumps(
            manifest_dict(
                name="demo",
                python="fake_plugin_impl:plugin",
                gates=[
                    {
                        "id": "gate:demo.ok",
                        "severity": "blocking",
                        "owner_agent": "ee-agent",
                        "after": [],
                        "handler": "gate_ok",
                    }
                ],
            )
        ),
        encoding="utf-8",
    )
    plugins = discover_from_project(tmp_path)
    assert len(plugins) == 1
    assert plugins[0].loaded
    assert plugins[0].handler("gate_ok") is not None


def test_discover_reports_missing_handler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    impl = tmp_path / "fake_plugin_impl2.py"
    impl.write_text("class Plugin:\n    pass\nplugin = Plugin()\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    manifest = make_manifest(
        name="demo",
        python="fake_plugin_impl2:plugin",
        gates=[
            {
                "id": "gate:demo.ok",
                "severity": "blocking",
                "owner_agent": "ee-agent",
                "after": [],
                "handler": "missing",
            }
        ],
    )
    plugin = load_plugin(manifest, source="test", root=tmp_path)
    assert not plugin.loaded
    assert "missing handler" in (plugin.error or "")


def test_discover_bad_manifest_isolated(tmp_path: Path) -> None:
    bad_dir = tmp_path / "plugins" / "broken"
    bad_dir.mkdir(parents=True)
    (bad_dir / "atomc-plugin.json").write_text("{not json", encoding="utf-8")
    plugins = discover_from_project(tmp_path)
    assert len(plugins) == 1
    assert not plugins[0].loaded
    assert plugins[0].name == "broken"


# --- registry ----------------------------------------------------------------


def test_registry_conflict_isolated(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    registry = PluginRegistry(store=store, events=EventBus(), project_root=tmp_path)
    registry.add(make_plugin("a", watches=[{"id": "shared:w", "ir": ["/electrical"]}]))
    second = registry.add(make_plugin("b", watches=[{"id": "shared:w", "ir": ["/electrical"]}]))
    assert not second.loaded
    assert "conflicts" in (second.error or "")
    statuses = {entry["name"]: entry for entry in registry.status_list()}
    assert statuses["a"]["loaded"] is True
    assert statuses["b"]["loaded"] is False


def test_tools_list_filters_by_agent(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    registry = PluginRegistry(store=store, events=EventBus(), project_root=tmp_path)
    registry.add(
        make_plugin(
            "demo",
            produces=["/sourcing"],
            tools=[
                {
                    "name": "search",
                    "description": "find",
                    "input_schema": {},
                    "agents": ["ee-agent"],
                    "mutates": False,
                    "handler": "search",
                },
                {
                    "name": "place",
                    "description": "order",
                    "input_schema": {},
                    "agents": ["ops-agent"],
                    "mutates": True,
                    "handler": "place",
                },
            ],
        )
    )
    assert [t["name"] for t in registry.tools_list(agent="ee-agent")] == ["search"]
    assert {t["name"] for t in registry.tools_list()} == {"search", "place"}


class _ToolPlugin:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search(self, ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
        self.calls.append("search")
        return {"result": {"hits": []}, "artifacts": []}

    async def write_out(self, ctx: Any, args: dict[str, Any]) -> str:
        await ctx.ir_transact("/electrical", 0, [{"op": "add", "path": "", "value": {}}])
        return "wrote"


async def test_call_tool_success(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    registry = PluginRegistry(store=store, events=EventBus(), project_root=tmp_path)
    obj = _ToolPlugin()
    registry.add(
        make_plugin(
            "demo",
            obj=obj,
            produces=["/sourcing"],
            tools=[
                {
                    "name": "search",
                    "description": "find",
                    "input_schema": {},
                    "agents": ["ee-agent"],
                    "mutates": False,
                    "handler": "search",
                }
            ],
        )
    )
    outcome = await registry.call_tool("demo", "search", {})
    assert outcome["result"] == {"hits": []}
    assert obj.calls == ["search"]


async def test_call_tool_scope_violation(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    registry = PluginRegistry(store=store, events=EventBus(), project_root=tmp_path)
    registry.add(
        make_plugin(
            "demo",
            obj=_ToolPlugin(),
            produces=["/sourcing"],
            tools=[
                {
                    "name": "write",
                    "description": "write",
                    "input_schema": {},
                    "agents": ["ee-agent"],
                    "mutates": True,
                    "handler": "write_out",
                }
            ],
        )
    )
    with pytest.raises(PluginFailureError) as exc_info:
        await registry.call_tool("demo", "write", {})
    assert exc_info.value.code == -32020
    assert "may not write" in exc_info.value.data["detail"]


async def test_scope_context_blocks_writes(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    registry = PluginRegistry(store=store, events=EventBus(), project_root=tmp_path)
    plugin = registry.add(make_plugin("demo", produces=["/sourcing"]))
    ctx = registry.make_context(plugin)
    with pytest.raises(ScopeError):
        await ctx.ir_transact("/electrical", 0, [{"op": "add", "path": "", "value": {}}])


def test_build_registry_from_project(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    registry = build_registry(tmp_path, store=store, events=EventBus(), include_entry_points=False)
    assert registry.status_list() == []
