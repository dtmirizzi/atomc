"""Plugin manifest models and validation for ``atomc-plugin.json`` (v0.1.0).

The frozen contract is ``docs/architecture/contracts/plugin-manifest.md``. This module is the
daemon's *local* parser so ``atomcd`` can discover and register plugins without a hard import of
``atomc-plugin-sdk`` (WP-2.2). When the SDK is installed, :func:`validate_manifest` prefers
``atomc_plugin_sdk.validate_manifest`` so both sides share one source of truth; otherwise the
models below enforce the same field rules.

The models deliberately mirror the contract, including ``extra="forbid"`` and cross-field
invariants (unique ids, allowed ``produces`` scopes, mutating tools require write scopes, …).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

MANIFEST_VERSION = "0.1.0"
MANIFEST_FILENAME = "atomc-plugin.json"

NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")

ALLOWED_PRODUCES_ROOTS = {
    "electrical",
    "layout",
    "keyboard",
    "firmware",
    "simulation",
    "mechanical",
    "sourcing",
    "fabrication",
    "orders",
    "gates",
    "provenance",
    "ext",
}
FORBIDDEN_PRODUCES_ROOTS = {"meta"}

SPECIALISTS = ("ee-agent", "fw-agent", "mech-agent", "ops-agent")
Severity = Literal["blocking", "advisory"]
OwnerAgent = Literal["ee-agent", "fw-agent", "mech-agent", "ops-agent"]


class ManifestError(ValueError):
    """A manifest is malformed or violates a cross-field invariant."""

    def __init__(self, message: str, errors: list[dict[str, str]] | None = None) -> None:
        self.errors = errors or []
        super().__init__(message)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Runtime(_Model):
    python: str | None = None
    ts: str | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> Runtime:
        if not self.python and not self.ts:
            raise ValueError("at least one of runtime.python or runtime.ts is required")
        return self


class Watch(_Model):
    id: str
    ir: list[str]
    files: list[str] = Field(default_factory=list)
    debounce_ms: int = Field(default=250, ge=0, le=60000)

    @model_validator(mode="after")
    def _check(self) -> Watch:
        if not self.id:
            raise ValueError("watch id must be non-empty")
        if not self.ir:
            raise ValueError(f"watch {self.id!r} requires at least one ir pointer")
        for pointer in self.ir:
            _validate_pointer(pointer, where=f"watch {self.id!r}")
        return self


class Gate(_Model):
    id: str
    severity: Severity
    owner_agent: OwnerAgent | None
    after: list[str] = Field(default_factory=list)
    handler: str

    @model_validator(mode="after")
    def _check(self) -> Gate:
        if not self.id.startswith("gate:"):
            raise ValueError(f"gate id {self.id!r} must start with 'gate:'")
        if not self.handler:
            raise ValueError(f"gate {self.id!r} requires a handler")
        return self


class Tool(_Model):
    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    agents: list[str] = Field(default_factory=list)
    mutates: bool = False
    handler: str

    @model_validator(mode="after")
    def _check(self) -> Tool:
        if not self.name:
            raise ValueError("tool name must be non-empty")
        if not self.handler:
            raise ValueError(f"tool {self.name!r} requires a handler")
        unknown = [a for a in self.agents if a not in SPECIALISTS]
        if unknown:
            raise ValueError(f"tool {self.name!r} has unknown agents {unknown}")
        return self


class CliCommand(_Model):
    command: str
    description: str
    handler: str


class UiPanel(_Model):
    panel: str
    title: str
    entry: str

    @model_validator(mode="after")
    def _check(self) -> UiPanel:
        if self.entry.startswith("/") or ".." in self.entry.split("/"):
            raise ValueError(f"ui entry {self.entry!r} must not escape the package root")
        return self


class Manifest(_Model):
    manifest_version: str
    name: str
    version: str
    description: str
    atomc: str
    runtime: Runtime
    watches: list[Watch] = Field(default_factory=list)
    produces: list[str] = Field(default_factory=list)
    gates: list[Gate] = Field(default_factory=list)
    tools: list[Tool] = Field(default_factory=list)
    cli: list[CliCommand] = Field(default_factory=list)
    ui: list[UiPanel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> Manifest:
        if self.manifest_version != MANIFEST_VERSION:
            raise ValueError(
                f"unsupported manifest_version {self.manifest_version!r}; "
                f"expected {MANIFEST_VERSION!r}"
            )
        if not NAME_RE.match(self.name):
            raise ValueError(f"plugin name {self.name!r} must be kebab-case")
        if not SEMVER_RE.match(self.version):
            raise ValueError(f"plugin version {self.version!r} must be SemVer")
        if not self.atomc.strip():
            raise ValueError("atomc must be a non-empty version range")
        _require_unique([w.id for w in self.watches], "watch id")
        _require_unique([g.id for g in self.gates], "gate id")
        _require_unique([t.name for t in self.tools], "tool name")
        _require_unique([c.command for c in self.cli], "cli command")
        _require_unique([u.panel for u in self.ui], "ui panel")
        for pointer in self.produces:
            _validate_pointer(pointer, where="produces")
            root = pointer.strip("/").split("/")[0]
            if root in FORBIDDEN_PRODUCES_ROOTS:
                raise ValueError(f"produces pointer {pointer!r} may not target /meta")
            if root not in ALLOWED_PRODUCES_ROOTS:
                raise ValueError(
                    f"produces pointer {pointer!r} must start with an allowed top-level node"
                )
        if any(t.mutates for t in self.tools) and not self.produces:
            raise ValueError("mutating tools require at least one produces scope")
        return self

    def gate(self, gate_id: str) -> Gate | None:
        for gate in self.gates:
            if gate.id == gate_id:
                return gate
        return None

    def tool(self, name: str) -> Tool | None:
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None


def _require_unique(values: list[str], label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"duplicate {label} {value!r}")
        seen.add(value)


def _validate_pointer(pointer: str, *, where: str) -> None:
    if not pointer.startswith("/"):
        raise ValueError(f"{where}: JSON pointer {pointer!r} must start with '/'")


def _coerce_manifest(value: Any) -> Manifest:
    """Convert an SDK validation result into the daemon's local :class:`Manifest`.

    ``atomc_plugin_sdk.validate_manifest`` returns the SDK's own ``PluginManifest`` class, which
    is a *different* Pydantic model. Feeding that instance straight into
    ``Manifest.model_validate`` fails, so dump it back to contract JSON first and validate the
    JSON against the local models (single wire contract, two class definitions).
    """
    if isinstance(value, Manifest):
        return value
    if isinstance(value, BaseModel):
        return Manifest.model_validate(value.model_dump(mode="json", by_alias=True))
    if isinstance(value, dict):
        return Manifest.model_validate(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json", by_alias=True)
        if isinstance(dumped, dict):
            return Manifest.model_validate(dumped)
    raise ManifestError(f"SDK validate_manifest returned unsupported value {type(value).__name__}")


def validate_manifest(data: dict[str, Any]) -> Manifest:
    """Validate raw manifest data into a :class:`Manifest`.

    Prefers ``atomc_plugin_sdk.validate_manifest`` when that package is importable so the daemon
    and SDK never disagree; the SDK result is coerced back to the local models via contract JSON.
    Falls back to the local contract models when the SDK is absent.
    """
    sdk = _load_sdk_validator()
    try:
        if sdk is not None:
            return _coerce_manifest(sdk(data))
        return Manifest.model_validate(data)
    except ValidationError as exc:
        errors = [
            {"path": "/".join(str(p) for p in err["loc"]), "message": err["msg"]}
            for err in exc.errors()
        ]
        raise ManifestError(f"invalid plugin manifest: {errors}", errors) from exc


def load_manifest(path: str | Path) -> Manifest:
    """Load and validate an ``atomc-plugin.json`` file."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ManifestError(f"manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError(f"manifest {path} must be a JSON object")
    return validate_manifest(data)


def _load_sdk_validator() -> Any | None:  # pragma: no cover - optional integration
    try:
        from atomc_plugin_sdk import validate_manifest as sdk_validate  # type: ignore[import-not-found,unused-ignore]
    except ImportError:
        return None
    return sdk_validate


__all__ = [
    "ALLOWED_PRODUCES_ROOTS",
    "MANIFEST_FILENAME",
    "MANIFEST_VERSION",
    "SPECIALISTS",
    "CliCommand",
    "Gate",
    "Manifest",
    "ManifestError",
    "Runtime",
    "Tool",
    "UiPanel",
    "Watch",
    "load_manifest",
    "validate_manifest",
]
