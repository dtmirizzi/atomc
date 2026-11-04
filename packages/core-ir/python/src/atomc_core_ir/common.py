"""Shared types for the atomc unified system IR (system_ir.json).

Implements the conventions in ``docs/architecture/contracts/ir-schema.md`` §1 and §2:
snake_case JSON keys, unit-annotated numeric aliases, ``<kind>:<slug>`` ids, RFC 3339 UTC
timestamps, ``sha256:<hex>`` hashes and the per-node ``_meta`` revision/lock envelope.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer

# ---------------------------------------------------------------------------
# Ids
# ---------------------------------------------------------------------------

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*:[A-Za-z0-9_.\-/]+$")
"""``<kind>:<slug>``, e.g. ``comp:U1``, ``net:3V3``, ``gate:erc.no_unconnected``."""

SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"


def validate_ir_id(value: str) -> str:
    """Validate the global IR id format. Raises ``ValueError`` on mismatch."""
    if not isinstance(value, str) or not ID_PATTERN.match(value):
        raise ValueError(
            f"invalid IR id {value!r}: expected '<kind>:<slug>' matching {ID_PATTERN.pattern}"
        )
    return value


IrId = Annotated[str, AfterValidator(validate_ir_id)]
"""Any id in the document. Uniqueness is checked document-wide by referential integrity."""

Sha256 = Annotated[str, Field(pattern=SHA256_PATTERN)]


# ---------------------------------------------------------------------------
# Timestamps (RFC 3339 UTC, e.g. 2026-11-04T23:00:00Z)
# ---------------------------------------------------------------------------


def ensure_utc(value: datetime) -> datetime:
    """Require timezone-aware datetimes and normalise them to UTC."""
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError("timestamp must be timezone-aware (RFC 3339 UTC)")
    return value.astimezone(UTC)


def format_rfc3339(value: datetime) -> str:
    """Serialise a UTC datetime as ``YYYY-MM-DDTHH:MM:SSZ`` (second precision)."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


Timestamp = Annotated[
    datetime,
    AfterValidator(ensure_utc),
    PlainSerializer(format_rfc3339, return_type=str, when_used="json"),
]
"""Aware datetime; serialises to an RFC 3339 UTC string ending in ``Z``."""


# ---------------------------------------------------------------------------
# Unit-annotated numeric aliases (units carried as JSON-schema metadata)
# ---------------------------------------------------------------------------

LengthMm = Annotated[float, Field(json_schema_extra={"unit": "mm"})]
AngleDeg = Annotated[float, Field(json_schema_extra={"unit": "deg"})]
CurrentMa = Annotated[float, Field(json_schema_extra={"unit": "mA"})]
VoltageV = Annotated[float, Field(json_schema_extra={"unit": "V"})]
TemperatureC = Annotated[float, Field(json_schema_extra={"unit": "degC"})]
DurationMs = Annotated[int, Field(json_schema_extra={"unit": "ms"})]
DurationUs = Annotated[int, Field(json_schema_extra={"unit": "us"})]
DurationS = Annotated[int, Field(json_schema_extra={"unit": "s"})]
DurationDays = Annotated[int, Field(json_schema_extra={"unit": "days"})]
MoneyMinor = Annotated[int, Field(json_schema_extra={"unit": "minor_currency_units"})]


# ---------------------------------------------------------------------------
# Base model + concurrency envelope
# ---------------------------------------------------------------------------


class AtomcModel(BaseModel):
    """Base for every IR model: forbid unknown keys, allow population by field name."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Lock(AtomcModel):
    """An advisory subtree lock held by an agent."""

    holder: str
    acquired_at: Timestamp
    expires_at: Timestamp
    reason: str | None = None


class NodeMeta(AtomcModel):
    """Per-top-level-node concurrency envelope (JSON key ``_meta``)."""

    rev: int = Field(default=0, ge=0)
    lock: Lock | None = None


def default_node_meta() -> NodeMeta:
    """Fresh ``_meta`` block for newly created top-level nodes."""
    return NodeMeta(rev=0, lock=None)


class Artifact(AtomcModel):
    """A produced file tracked by the IR."""

    id: IrId
    kind: Literal[
        "elf",
        "bin",
        "uf2",
        "step",
        "stl",
        "glb",
        "png",
        "repl",
        "resc",
        "csv",
        "json",
        "other",
    ]
    path: str
    sha256: Sha256
    bytes: int = Field(ge=0)
    produced_by: str | None = None
    produced_at: Timestamp


Point2 = Annotated[list[float], Field(min_length=2, max_length=2)]
"""A 2D coordinate ``[x, y]``. JSON arrays validate directly (no tuple coercion needed)."""

Point3 = Annotated[list[float], Field(min_length=3, max_length=3)]
"""A 3D coordinate ``[x, y, z]``."""

Polygon = Annotated[list[Point2], Field(min_length=3)]
"""A closed polygon ring with at least three vertices (implicitly closed)."""


JSONValue = Any
"""Arbitrary JSON value used by plugin extension points (``*.ext`` dicts)."""
