# `@atomc/cli` — the `atomc` command-line client

The CLI scaffolds projects and talks to `atomcd` through the authenticated JSON-RPC client. It uses Commander 15 and the shared `@atomc/daemon-client`, `@atomc/core-ir` and `@atomc/plugin-sdk` packages. This is a pre-alpha source package; it has not been published to npm.

## Install

```bash
npx @atomc/cli --help       # once published
# or, from this repo:
pnpm --filter @atomc/cli build
node apps/atomc-cli/dist/index.js --help
```

The binary name is `atomc` when invoked from the built package. Until publication, run the repository build shown above.

## Commands

| Command                            | Status   | Description                                                                                                        |
| ---------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------ |
| `atomc init <dir>`                 | working  | scaffold a project from `examples/atomc-pad` (or `--template <name>`); refuses a non-empty target unless `--force` |
| `atomc doctor`                     | working  | check the CLI, running daemon/schema, plugin load, and local toolchains                                            |
| `atomc daemon start\|status\|stop` | working  | manage the `atomcd` daemon via `@atomc/daemon-client`                                                              |
| `atomc plugin list`                | working  | list plugins loaded by the daemon (`--json`)                                                                       |
| `atomc plugin new <name>`          | working  | scaffold a manifest + entrypoint + test, validated by `@atomc/plugin-sdk`                                          |
| `atomc build [target]`             | working  | start/attach to daemon, request DAG run, wait for status and report actual gates. Hardware outputs require plugins. |
| `atomc sim`                        | stub     | Renode simulation — reports `unavailable`/`not_implemented`, never PASS                                            |
| `atomc jig`                        | stub     | pogo jig / plate / case generation — reports status, never PASS                                                    |
| `atomc quote`                      | stub     | BOM + fab quotes — reports status, never PASS                                                                      |
| `atomc orders`                     | stub     | order placement — reports status, never PASS                                                                       |
| `atomc converge`                   | working* | invokes a trusted convergence runtime; reports honest unavailable status when none is configured                   |

Implemented commands support `--json`. They emit one JSON object on stdout; diagnostics go to
stderr. Stub commands return structured status and exit 3. *The CLI package does not configure a
model runtime by default, so `converge` returns `unavailable` until a trusted host injects one.

### Exit codes

| Code | Meaning                                                              |
| ---- | -------------------------------------------------------------------- |
| `0`  | success                                                              |
| `1`  | error, failed build, or doctor `FAIL`                                |
| `3`  | capability unavailable (`plugin` missing or feature not implemented) |

## Configuration

Project templates include `atomc.config.ts`, but this CLI version does not load typed project configuration into command behavior. Daemon commands use the current working directory or an explicit `--project <dir>` where supported.

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

- `sim`, `jig`, `quote`, and `orders` are intentionally stubs. They report a structured
  `unavailable`/`not_implemented` result and exit `3`; they never report a fake `PASS`. They will
  be wired to plugins in Phases 4–5.
- `converge` uses an injected `ConvergenceRuntime`; without one, it reports structured
  `unavailable` and exits `3`. Incomplete convergence exits `1`; only final daemon gate state with
  no blocking FAIL/ERROR exits `0`.
- `atomc.config.ts` is a project convention. This CLI version does not load typed project
  configuration into the commands.
- The package version must stay lock-step with `scripts/release/VERSION`.
