# Contract: GateResult (v0.1) — FROZEN for Phase 1

```jsonc
{
  "id": "gate:bom.all_in_stock",
  "status": "PASS" | "FAIL" | "SKIP" | "ERROR",
  "severity": "blocking" | "advisory",          // advisory FAIL never blocks convergence
  "plugin": "plugin:sourcing@0.1.0",
  "owner_agent": "ee-agent" | "fw-agent" | "mech-agent" | "ops-agent" | null,
  "evaluated_at": "2026-11-04T23:00:00Z",
  "ir_rev": 42,                                  // document rev the gate evaluated
  "duration_ms": 120,
  "summary": "2 BOM lines out of stock",
  "evidence": [ { "kind": "text"|"json"|"artifact"|"image", "ref"?: "art:…", "data"?: any, "message"?: str } ],
  "suggestions": [ { "message": str, "patch"?: { "path": str, "ops": [JsonPatchOp] } } ],
  "refs": ["comp:U3", "bom:…"]                   // IR ids implicated
}
```

Rules: gates are deterministic given (IR rev, artifacts, cached external data with `fetched_at`).
`ERROR` = gate itself crashed (wakes the orchestrator, not a domain agent). Stored in IR at
`/gates/results/<id without prefix>`.
