"""Conformance checks for plugin implementations.

``conformance(plugin)`` validates a plugin's manifest and checks that every declared gate, tool
and CLI handler is implemented and callable, rejecting undeclared handlers when the plugin
exposes an explicit registry. It is dependency-free (no daemon, network or hardware) and returns
a structured :class:`ConformanceReport`; :func:`assert_conformance` raises
:class:`PluginConformanceError` on the first failure.

The ``plugin`` argument may be a :class:`~atomc_plugin_sdk.plugin.PluginDefinition`, a decorated
class, a decorated factory function, or a decorated instance. Factory functions are invoked to
obtain an instance, so conformance is an execution-time check (as in the TypeScript SDK).
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .errors import ConformanceFinding, ManifestValidationError, PluginConformanceError
from .manifest import (
    ALLOWED_PRODUCES_NODES,
    PluginManifest,
    validate_manifest,
)
from .plugin import HANDLERS_ATTR, PluginDefinition, get_handlers, get_manifest

__all__ = [
    "ConformanceReport",
    "assert_conformance",
    "conformance",
]


@dataclass(frozen=True, slots=True)
class ConformanceReport:
    """Structured result of a conformance run."""

    plugin_name: str
    findings: tuple[ConformanceFinding, ...] = ()

    @property
    def ok(self) -> bool:
        """True when no error-severity finding was produced."""
        return not any(finding.severity == "error" for finding in self.findings)

    @property
    def errors(self) -> tuple[ConformanceFinding, ...]:
        return tuple(f for f in self.findings if f.severity == "error")

    @property
    def warnings(self) -> tuple[ConformanceFinding, ...]:
        return tuple(f for f in self.findings if f.severity == "warning")

    def raise_if_invalid(self) -> None:
        """Raise :class:`PluginConformanceError` when any error-severity finding exists."""
        if not self.ok:
            raise PluginConformanceError(self.plugin_name, list(self.errors))


def conformance(plugin: Any) -> ConformanceReport:
    """Run manifest and implementation conformance checks for ``plugin``."""
    findings: list[ConformanceFinding] = []

    manifest, explicit_handlers, target, name = _resolve(plugin, findings)
    if manifest is None:
        return ConformanceReport(plugin_name=name or "<unknown>", findings=tuple(findings))

    try:
        manifest = _revalidate(manifest)
    except ManifestValidationError as exc:
        for error in exc.errors:
            findings.append(
                ConformanceFinding(
                    code="MANIFEST_INVALID",
                    message=error.message,
                    path=error.path or None,
                )
            )
        return ConformanceReport(plugin_name=manifest.name, findings=tuple(findings))

    findings.extend(_duplicate_findings(manifest))
    findings.extend(_produces_findings(manifest))
    findings.extend(_definition_findings(manifest))

    declared = manifest.handler_names
    declared_set = set(declared)

    if explicit_handlers is not None:
        for undeclared in sorted(set(explicit_handlers) - declared_set):
            findings.append(
                ConformanceFinding(
                    code="UNDECLARED_HANDLER",
                    message=(
                        f"handler {undeclared!r} is registered but not declared by any gate, "
                        "tool or CLI command"
                    ),
                    path=f"/{HANDLERS_ATTR}/{undeclared}",
                )
            )

    for position, handler_name in enumerate(declared):
        if explicit_handlers is not None:
            candidate = explicit_handlers.get(handler_name)
        else:
            candidate = getattr(target, handler_name, None) if target is not None else None
        if candidate is None:
            findings.append(
                ConformanceFinding(
                    code="MISSING_HANDLER",
                    message=f"declared handler {handler_name!r} is not implemented",
                    path=f"/handlers/{handler_name}",
                )
            )
            del position
        elif not callable(candidate):
            findings.append(
                ConformanceFinding(
                    code="HANDLER_NOT_CALLABLE",
                    message=f"declared handler {handler_name!r} is not callable",
                    path=f"/handlers/{handler_name}",
                )
            )

    return ConformanceReport(plugin_name=manifest.name, findings=tuple(findings))


def assert_conformance(plugin: Any) -> PluginManifest:
    """Run conformance and raise :class:`PluginConformanceError` on failure.

    On success returns the validated manifest, so callers can chain ``assert_conformance(p)``.
    """
    report = conformance(plugin)
    report.raise_if_invalid()
    manifest, _, _, _ = _resolve(plugin, [])
    assert manifest is not None
    return _revalidate(manifest)


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------


def _resolve(
    plugin: Any,
    findings: list[ConformanceFinding],
) -> tuple[PluginManifest | None, Mapping[str, Any] | None, Any, str]:
    """Return ``(manifest, explicit_handlers, target, name)`` for any plugin form."""
    if isinstance(plugin, PluginDefinition):
        return plugin.manifest, plugin.handlers or None, plugin, plugin.manifest.name

    raw_manifest = get_manifest(plugin)
    if raw_manifest is None:
        findings.append(
            ConformanceFinding(
                code="NO_MANIFEST",
                message=(
                    "object has no __atomc_manifest__; decorate it with @atomc_plugin or pass "
                    "a PluginDefinition"
                ),
            )
        )
        return None, None, None, getattr(plugin, "__name__", type(plugin).__name__)

    if isinstance(raw_manifest, Mapping):
        try:
            manifest = validate_manifest(raw_manifest)
        except ManifestValidationError as exc:
            for error in exc.errors:
                findings.append(
                    ConformanceFinding(
                        code="MANIFEST_INVALID",
                        message=error.message,
                        path=error.path or None,
                    )
                )
            return None, None, None, str(raw_manifest.get("name", "<unknown>"))
    elif isinstance(raw_manifest, PluginManifest):
        manifest = raw_manifest
    else:
        findings.append(
            ConformanceFinding(
                code="MANIFEST_INVALID",
                message=(
                    "__atomc_manifest__ must be a PluginManifest, got "
                    f"{type(raw_manifest).__name__}"
                ),
            )
        )
        return None, None, None, ""

    explicit_handlers = get_handlers(plugin)
    name = manifest.name

    if inspect.isclass(plugin):
        return manifest, explicit_handlers, plugin, name
    if not inspect.isfunction(plugin) and not inspect.ismethod(plugin) and callable(plugin):
        return manifest, explicit_handlers, plugin, name
    if inspect.isfunction(plugin) or inspect.ismethod(plugin):
        try:
            instance = plugin()
        except Exception as exc:
            findings.append(
                ConformanceFinding(
                    code="FACTORY_ERROR",
                    message=f"plugin factory raised {type(exc).__name__}: {exc}",
                )
            )
            return manifest, explicit_handlers, None, name
        return manifest, explicit_handlers, instance, name
    return manifest, explicit_handlers, plugin, name


def _revalidate(manifest: PluginManifest) -> PluginManifest:
    """Re-run full validation (including cross-field rules) on a typed manifest."""
    return validate_manifest(manifest.model_dump(mode="json"))


def _duplicate_findings(manifest: PluginManifest) -> list[ConformanceFinding]:
    checks: list[tuple[str, str, list[str]]] = [
        ("watch", "/watches", [w.id for w in manifest.watches]),
        ("gate", "/gates", [g.id for g in manifest.gates]),
        ("tool", "/tools", [t.name for t in manifest.tools]),
        ("CLI command", "/cli", [c.command for c in manifest.cli]),
        ("UI panel", "/ui", [u.panel for u in manifest.ui]),
    ]
    findings: list[ConformanceFinding] = []
    for kind, base, values in checks:
        seen: dict[str, int] = {}
        for index, value in enumerate(values):
            if value in seen:
                findings.append(
                    ConformanceFinding(
                        code="DUPLICATE_DECLARATION",
                        message=(
                            f"duplicate {kind} identifier {value!r} "
                            f"(first declared at {base}/{seen[value]})"
                        ),
                        path=f"{base}/{index}",
                    )
                )
            else:
                seen[value] = index
    return findings


def _produces_findings(manifest: PluginManifest) -> list[ConformanceFinding]:
    findings: list[ConformanceFinding] = []
    for index, pointer in enumerate(manifest.produces):
        node = pointer.split("/", 2)[1] if pointer.startswith("/") else ""
        if node == "meta" or node not in ALLOWED_PRODUCES_NODES:
            findings.append(
                ConformanceFinding(
                    code="INVALID_PRODUCES",
                    message=f"{pointer!r} is not a permitted write scope",
                    path=f"/produces/{index}",
                )
            )
    return findings


def _definition_findings(manifest: PluginManifest) -> list[ConformanceFinding]:
    findings: list[ConformanceFinding] = []
    for index, tool in enumerate(manifest.tools):
        # A JSON Schema may be an object or a boolean; anything else is malformed.
        if not isinstance(tool.input_schema, (dict, bool)):
            findings.append(
                ConformanceFinding(
                    code="MALFORMED_TOOL",
                    message=f"tool {tool.name!r} input_schema must be a JSON Schema",
                    path=f"/tools/{index}/input_schema",
                )
            )
        if tool.mutates and not manifest.produces:
            findings.append(
                ConformanceFinding(
                    code="MALFORMED_TOOL",
                    message=(
                        f"mutating tool {tool.name!r} does not declare any 'produces' write scope"
                    ),
                    path=f"/tools/{index}/mutates",
                )
            )
    for index, gate in enumerate(manifest.gates):
        if not gate.handler.strip():
            findings.append(
                ConformanceFinding(
                    code="MALFORMED_GATE",
                    message=f"gate {gate.id!r} has an empty handler",
                    path=f"/gates/{index}/handler",
                )
            )
    return findings
