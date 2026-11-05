# @atomc/cli — the `atomc` command-line interface

The `atomc` CLI drives the atomc hardware compiler: it bootstraps projects, talks to the
`atomcd` daemon over its authenticated JSON-RPC socket, and reports DAG/gate results. It is
built on [Commander 15](https://github.com/tj/commander.js) and reuses the merged
`@atomc/daemon-client`, `@atomc/core-ir`, and `@atomc/plugin-sdk` packages — it does **not**
re-implement the RPC client or the Python daemon.

## Install

```bash
npx @atomc/cli --help       # once published
# or, from this repo:
pnpm --filter @atomc/cli build
node apps/atomc-cli/dist/index.js --help
```

The binary name is `atomc`.

## Commands

| Command                            | Status  | Description                                                                                                        |
| ---------------------------------- | ------- | ------------------------------------------------------------------------------------------------------------------ |
| `atomc init <dir>`                 | working | scaffold a project from `examples/atomc-pad` (or `--template <name>`); refuses a non-empty target unless `--force` |
| `atomc doctor`                     | working | check the CLI, running daemon/schema, plugin load, and local toolchains                                            |
| `atomc daemon start\|status\|stop` | working | manage the `atomcd` daemon via `@atomc/daemon-client`                                                              |
| `atomc plugin list`                | working | list plugins loaded by the daemon (`--json`)                                                                       |
| `atomc plugin new <name>`          | working | scaffold a manifest + entrypoint + test, validated by `@atomc/plugin-sdk`                                          |
| `atomc build [target]`             | working | run the daemon DAG, poll to completion, print node + gate summary                                                  |
| `atomc sim`                        | planned | Renode simulation — reports `unavailable`/`not_implemented`, never PASS                                            |
| `atomc jig`                        | planned | pogo jig / plate / case generation — reports status, never PASS                                                    |
| `atomc quote`                      | planned | BOM + fab quotes — reports status, never PASS                                                                      |
| `atomc orders`                     | planned | order placement — reports status, never PASS                                                                       |
| `atomc converge`                   | planned | multi-agent swarm until gates pass — reports status, never PASS                                                    |

Every command supports `--json`. With `--json`, stdout contains exactly one JSON object and
all diagnostics go to stderr.

### Exit codes

| Code | Meaning                                                                          |
| ---- | -------------------------------------------------------------------------------- |
| `0`  | success                                                                          |
| `1`  | error, failed build, or doctor `FAIL`                                            |
| `3`  | capability planned but unavailable (`plugin` missing or feature not implemented) |

## Configuration

Projects may carry an `atomc.config.ts` (see `examples/atomc-pad/atomc.config.ts`) describing
the project name, daemon host/port, enabled plugins, and budget gates. Commands that need the
daemon use the current working directory (or `--project <dir>`) as the project root.

## Development

```bash
pnpm --filter @atomc/cli test          # Vitest, fakes only (no daemon/network/hardware)
pnpm --filter @atomc/cli test:coverage # ≥85% lines
pnpm --filter @atomc/cli typecheck
pnpm --filter @atomc/cli lint
pnpm --filter @atomc/cli build
pnpm exec biome check apps/atomc-cli
```

All command handlers take an injected `CliDeps` object (`src/deps.ts`), so tests drive the
whole command tree with an in-memory filesystem and a scripted `DaemonApi` fake.

## Current scope limitations

- `sim`, `jig`, `quote`, `orders`, and `converge` are intentionally stubs. They report a
  structured `unavailable`/`not_implemented` result and exit `3`; they never report a fake
  `PASS`. They will be wired to plugins in Phases 4–5 and to `@atomc/swarm-harness` in WP-3.4.
- `atomc.config.ts` is an established project convention; command-specific config loading is
  minimal in this version (project root resolution only).
- The package version must stay lock-step with `scripts/release/VERSION`.
