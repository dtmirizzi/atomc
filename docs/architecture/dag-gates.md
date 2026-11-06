# DAG & gates

The daemon provides the DAG and gate interfaces used by builds. Plugin manifests declare watches,
produces scopes and gates, though the hardware plugin implementations that populate a real project
graph and evaluate the planned checks have not landed yet.

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

The Python daemon includes `networkx` scheduling, file-watch support, run state and provenance bookkeeping. Project nodes and artifact producers depend on the planned domain plugins.

You can inspect and drive the graph over RPC: `dag.status` and `dag.run(targets?, force?)`. See the
[RPC contract](/architecture/contracts/rpc).

## Gates

The gate runner returns a contract-shaped [`GateResult`](/architecture/contracts/gate-result) for a check over IR revision, artifacts and cached external data. The initial domain gate IDs below are the target contract; most corresponding plugin checks are still planned.

<GateBadge status="PASS" /> everything is fine ·
<GateBadge status="FAIL" /> a domain agent owns the fix ·
<GateBadge status="SKIP" /> not applicable ·
<GateBadge status="ERROR" /> the gate itself crashed (wakes the orchestrator)

A gate result may carry `owner_agent`. The deterministic harness can run one configured session and verify its gate results. The built-in specialist registry and automatic failure router are still planned.

### Initial gate set

| Gate id                                                                                          | Plugin       | Wakes                      |
| ------------------------------------------------------------------------------------------------ | ------------ | -------------------------- |
| `erc.no_unconnected`, `erc.assertions`                                                           | atopile      | `@ee-agent`                |
| `layout.testpads.min_count`, `layout.testpads.nets_covered`                                      | atopile      | `@ee-agent`                |
| `fw.qmk_compile`, `fw.tests.pass`, `fw.boot_banner`, `fw.matrix_scan`, `fw.matrix_pins_match_ir` | renode / qmk | `@fw-agent`                |
| `kb.layout_matches_keymap`, `kb.diode_per_switch`, `kb.usb_cc_pulldowns`                         | atopile      | `@ee-agent`                |
| `mech.plate_switch_cutouts_14mm`, `mech.case_usb_cutout_aligned`                                 | cad-jig      | `@mech-agent`              |
| `mech.pogo_spacing_ge_2p54`, `mech.jig_no_collision`, `mech.enclosure_clearance`                 | cad-jig      | `@mech-agent`              |
| `bom.all_in_stock`, `bom.cost_under_budget`, `bom.lead_time_under_days`                          | sourcing     | `@ops-agent` + `@ee-agent` |
| `fab.quote_under_budget`                                                                         | sourcing     | `@ops-agent`               |

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
  "evidence": [{ "kind": "text", "message": "C12345 stock=0" }],
  "suggestions": [{ "message": "swap to C67890", "patch": { "path": "/sourcing/bom", "ops": [] } }],
  "refs": ["bom:…"]
}
```

In the harness core, advisory failures do not block an individual run; blocking failures lead to a bounded `RETRY` or `ESCALATE`. The `atomc converge` coordinator that repeatedly routes gate failures to specialists is still planned. See the [swarm status](/architecture/swarm).
