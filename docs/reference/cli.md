# CLI

::: info Planned
The `atomc` CLI is **planned** for Phase 3 (WP-3.1). The command surface below is the target from
[PLAN §8](/plan/master). It will be built with `commander` 15 and support `--json` for scripting.
:::

```bash
npx @atomc/cli <command> [options]
```

## Commands

| Command | Purpose |
| ------- | ------- |
| `init <name>` | Scaffold a new project: `system_ir.json`, `atomc.config.ts`, example sources |
| `build` | Start/attach the daemon and run the hardware DAG |
| `sim` | Run Renode emulation and test suites |
| `jig` | Generate the pogo-pin test jig and enclosure |
| `quote` | Fetch fab + assembly quotes for the current layout |
| `orders` | Inspect and manage the orders ledger |
| `converge` | Run the swarm until all blocking gates pass (`--max-cost`) |
| `doctor` | Verify CLI/daemon/plugin versions and that kernels + external tools are present |
| `daemon start\|stop\|status` | Manage the background `atomcd` process |
| `plugin new\|list` | Scaffold or list plugins |

## Global options

| Option | Meaning |
| ------ | ------- |
| `--json` | Emit machine-readable JSON instead of TTY output |
| `--verbose` | Increase log detail |
| `--config <path>` | Path to `atomc.config.ts` (defaults to the project root) |

## Config

`atomc.config.ts` is loaded with `tsx`/`jiti` and holds project defaults such as budget gates:

```ts
export default {
  gates: {
    "bom.cost_under_budget": { per_board_minor: 4500, qty: 5 },
  },
};
```

The full CLI reference is generated from `commander` once WP-3.1 lands.
