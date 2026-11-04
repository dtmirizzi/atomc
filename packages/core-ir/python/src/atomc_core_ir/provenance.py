"""``provenance`` domain node — DAG node inputs/outputs hashes."""

from __future__ import annotations

from pydantic import Field

from .common import AtomcModel, DurationMs, NodeMeta, Sha256, Timestamp


class ProvNode(AtomcModel):
    producer: str
    inputs_hash: Sha256
    outputs_hash: Sha256
    ran_at: Timestamp
    duration_ms: DurationMs = Field(ge=0)


class Provenance(AtomcModel):
    meta_: NodeMeta = Field(alias="_meta")
    nodes: dict[str, ProvNode] = Field(default_factory=dict)
