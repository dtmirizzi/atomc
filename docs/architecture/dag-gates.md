# DAG & gates

The daemon does two things on every build: it **schedules** work through a content-hashed graph, and
it **verifies** the result with deterministic gates.

## The reactive DAG

Plugins do not hard-code dependencies. Each plugin manifest declares what it watches:

```jsonc
"watches": [
  { "id": "bom-refresh", "ir": ["/electrical/components"], "files": ["**/*.ato"], "debounce_ms": 500 }
],
"produces": ["/sourcing", "/fabrication"]
```

- Each `watches[].id` becomes a **DAG node**.
- Edges are inferred: a node that watches an IR pointer is downstream of the plugin that `produces`
  it; file globs add file-level edges.
- Every node's inputs are **content-hashed**. When a file or IR subtree changes, only nodes whose
  hashes changed are marked `stale` and re-run. The rest stay `ok`.

`networkx` backs the graph; `watchfiles` drives incremental rebuilds. Provenance for each node —
inputs hash, outputs hash, producer plugin + version, run time — lands in `/provenance`.

You can inspect and drive the graph over RPC: `dag.status` and `dag.run(targets?, force?)`. See the
[RPC contract](/architecture/contracts/rpc).

## Gates

A gate is a deterministic check over `(IR rev, artifacts, cached external data)`. It returns a
[`GateResult`](/architecture/contracts/gate-result):

<GateBadge status="PASS" /> everything is fine ·
<GateBadge status="FAIL" /> a domain agent owns the fix ·
<GateBadge status="SKIP" /> not applicable ·
<GateBadge status="ERROR" /> the gate itself crashed (wakes the orchestrator)

A gate result carries `owner_agent`, so a failure routes itself to `@ee-agent`, `@fw-agent`,
`@mech-agent` or `@ops-agent`.

### Initial gate set

| Gate id | Plugin | Wakes |
| ------- | ------ | ----- |
| `erc.no_unconnected`, `erc.assertions` | atopile | `@ee-agent` |
| `layout.testpads.min_count`, `layout.testpads.nets_covered` | atopile | `@ee-agent` |
| `fw.qmk_compile`, `fw.tests.pass`, `fw.boot_banner`, `fw.matrix_scan`, `fw.matrix_pins_match_ir` | renode / qmk | `@fw-agent` |
| `kb.layout_matches_keymap`, `kb.diode_per_switch`, `kb.usb_cc_pulldowns` | atopile | `@ee-agent` |
| `mech.plate_switch_cutouts_14mm`, `mech.case_usb_cutout_aligned` | cad-jig | `@mech-agent` |
| `mech.pogo_spacing_ge_2p54`, `mech.jig_no_collision`, `mech.enclosure_clearance` | cad-jig | `@mech-agent` |
| `bom.all_in_stock`, `bom.cost_under_budget`, `bom.lead_time_under_days` | sourcing | `@ops-agent` + `@ee-agent` |
| `fab.quote_under_budget` | sourcing | `@ops-agent` |

### Reading a gate result

```jsonc
{
  "id": "gate:bom.all_in_stock",
  "status": "FAIL",
  "severity": "blocking",
  "plugin": "plugin:sourcing@0.1.0",
  "owner_agent": "ops-agent",
  "evaluated_at": "2026-11-04T23:00:00Z",
  "ir_rev": 42,
  "duration_ms": 120,
  "summary": "2 BOM lines out of stock",
  "evidence": [ { "kind": "text", "message": "C12345 stock=0" } ],
  "suggestions": [ { "message": "swap to C67890", "patch": { "path": "/sourcing/bom", "ops": [] } } ],
  "refs": ["bom:…"]
}
```

`advisory` failures never block convergence. `blocking` failures do — and they are exactly what wakes
the [swarm](/architecture/swarm).
