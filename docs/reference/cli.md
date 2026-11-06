# CLI

The `atomc` CLI is implemented in `apps/atomc-cli` with Commander 15. `init`, `build`, `doctor`, daemon management and plugin scaffolding/listing have handlers. Hardware-dependent commands are structured stubs until their plugins land; they return status/error information and never a fake PASS. The CLI is not published on npm yet.

```bash
pnpm --filter @atomc/cli build
node apps/atomc-cli/dist/index.js <command> [options]
```

## Commands

| Command                         | Current behavior                                                                                                    |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `init <dir>`                    | Copy the atomc-pad template, update project identity and guard existing files.                                      |
| `build [target]`                | Start/attach to daemon, request DAG run, wait for status and report actual gates. Hardware outputs require plugins. |
| `doctor`                        | Report CLI, daemon/schema and local toolchain checks.                                                               |
| `daemon start\|status\|stop`    | Ensure, inspect or shut down the daemon.                                                                            |
| `plugin list`                   | List daemon-discovered plugins.                                                                                     |
| `plugin new <name>`             | Scaffold a manifest and entrypoints validated by the SDK.                                                           |
| `sim`, `jig`, `quote`, `orders` | Structured capability stubs; exit 3 and never report PASS.                                                          |
| `converge`                      | Implemented on `wp/3.4-harness-converge` (under review): runs an injected convergence runtime; honest `unavailable` (exit 3) without one. |

## Options

Implemented commands expose their own options. Common examples are `--json`, `--project <dir>`, `--force`, build `--timeout <ms>`, and `plugin new --runtime ts|python|both`. Run `atomc <command> --help` for exact syntax. There is no global `--verbose` or typed project-config loader yet.

## Project configuration

`atomc.config.ts` is included in project templates, but the CLI does not yet load it as typed runtime configuration. A target shape is:

```ts
export default {
  gates: {
    "bom.cost_under_budget": { per_board_minor: 4500, qty: 5 },
  },
};
```

The package README documents current limitations. In particular, plugin-dependent commands remain explicit stubs until their backends are implemented.
