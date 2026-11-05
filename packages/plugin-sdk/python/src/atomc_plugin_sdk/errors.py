"""Exceptions and structured findings used across the atomc plugin SDK.

All errors carry stable, path-oriented detail so the daemon and the CLI can render
actionable manifest diagnostics without parsing prose. JSON pointers follow RFC 6901;
an empty string (``""``) denotes the manifest root.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = [
    "ConformanceFinding",
    "ManifestError",
    "ManifestValidationError",
    "PluginConformanceError",
    "SchemaNotFoundError",
]

Severity = Literal["error", "warning"]


@dataclass(frozen=True, slots=True)
class ManifestError:
    """A single manifest validation failure at a stable JSON-pointer path."""

    path: str
    message: str
    validator: str | None = None

    def __str__(self) -> str:
        where = self.path or "(root)"
        return f"{where}: {self.message}"


class ManifestValidationError(ValueError):
    """Raised when an ``atomc-plugin.json`` document fails validation.

    ``errors`` is ordered and de-duplicated; each entry carries a JSON-pointer ``path``,
    a human ``message`` and, when available, the JSON Schema ``validator`` keyword that
    rejected the document.
    """

    def __init__(self, errors: list[ManifestError]) -> None:
        self.errors = errors
        summary = "; ".join(str(err) for err in errors) if errors else "invalid manifest"
        super().__init__(f"invalid atomc plugin manifest: {summary}")


class SchemaNotFoundError(FileNotFoundError):
    """Raised when the shared WP-2.1 manifest JSON Schema cannot be located."""


@dataclass(frozen=True, slots=True)
class ConformanceFinding:
    """A single conformance check result for a plugin implementation."""

    code: str
    message: str
    path: str | None = None
    severity: Severity = "error"

    def __str__(self) -> str:
        where = f" at {self.path}" if self.path else ""
        return f"[{self.severity}] {self.code}{where}: {self.message}"


class PluginConformanceError(RuntimeError):
    """Raised when a plugin implementation fails conformance checks."""

    def __init__(self, plugin_name: str, findings: list[ConformanceFinding]) -> None:
        self.plugin_name = plugin_name
        self.findings: list[ConformanceFinding] = list(findings)
        details = "; ".join(str(f) for f in findings) if findings else "no details"
        super().__init__(f"plugin {plugin_name!r} failed conformance: {details}")
