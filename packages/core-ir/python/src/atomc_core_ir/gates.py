"""``gates`` domain node — deterministic verification results.

Implements ``docs/architecture/contracts/gate-result.md``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from .common import AtomcModel, DurationMs, IrId, NodeMeta, Timestamp


class Evidence(AtomcModel):
    kind: Literal["text", "json", "artifact", "image"]
    ref: IrId | None = None
    data: Any = None
    message: str | None = None


class SuggestionPatch(AtomcModel):
    path: str
    ops: list[dict[str, Any]] = Field(default_factory=list)


class Suggestion(AtomcModel):
    message: str
    patch: SuggestionPatch | None = None


class GateResult(AtomcModel):
    id: IrId
    status: Literal["PASS", "FAIL", "SKIP", "ERROR"]
    severity: Literal["blocking", "advisory"] = "blocking"
    plugin: str
    owner_agent: Literal["ee-agent", "fw-agent", "mech-agent", "ops-agent"] | None = None
    evaluated_at: Timestamp
    ir_rev: int = Field(ge=0)
    duration_ms: DurationMs = Field(default=0, ge=0)
    summary: str = ""
    evidence: list[Evidence] = Field(default_factory=list)
    suggestions: list[Suggestion] = Field(default_factory=list)
    refs: list[IrId] = Field(default_factory=list)


class Gates(AtomcModel):
    meta_: NodeMeta = Field(alias="_meta")
    results: dict[str, GateResult] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_result_keys(self) -> Gates:
        for key, result in self.results.items():
            expected = result.id.removeprefix("gate:")
            if key != expected:
                raise ValueError(
                    f"gate result key {key!r} must equal id {result.id!r} "
                    f"without the 'gate:' prefix ({expected!r})"
                )
        return self
