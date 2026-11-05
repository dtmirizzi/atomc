# WP-3.1 `cli` — `atomc` TypeScript CLI

Read `_common.md`, PLAN §§3, 5, 6, 8, 9 and `docs/architecture/contracts/{rpc,plugin-manifest,ir-schema}.md` fully. Phase 2 daemon, plugin SDK, and client are merged; use their public APIs. Do not implement a second RPC client or Python daemon.

## Owned paths
- `apps/atomc-cli/**`
- `docs/plan/handoffs/WP-3.1.md`

Do not edit root workspace files, lockfiles, daemon/client/SDK packages or contracts. The `apps/*` workspace glob already picks this up; report lockfile importer needs for the orchestrator.

## Deliverables
1. Private-source package `@atomc/cli` (publishable; npm binary name `atomc`) with Commander 15, `@atomc/daemon-client`, `@atomc/core-ir`, `@atomc/plugin-sdk`, and `tsx` only as needed. Catalog dependencies where available. Build via tsup into executable ESM + CJS with a `bin` entry; `npx @atomc/cli` and `node dist/index.js` must work. Bump-compatible package version must match `scripts/release/VERSION` (0.0.1); do not bump independently.
2. Command tree per PLAN §3: `init`, `build`, `sim`, `jig`, `quote`, `orders`, `converge`, `doctor`, `daemon {start,status,stop}`, `plugin {list,new}`. Implement working `doctor`, daemon status/start/stop, `init`, and `plugin list/new`; hardware-dependent build/sim/jig/quote/orders/converge commands should call the daemon and return structured, actionable “plugin not installed/not implemented yet” responses, never fake PASS.
3. Inject dependencies (`DaemonClient`/`ensureDaemon`, project resolver, filesystem, stdout/stderr, clock) behind a small interface so unit tests use fakes and never spawn a real daemon or access network/hardware.
4. `init <dir>`: refuse overwriting existing non-empty dir unless `--force`; copy the merged `examples/atomc-pad` template or generate a lightweight project starter; set a unique project name/id; run `atomc doctor` and print next steps. Avoid copying generated `build/`, `.venv`, node_modules or QMK build artifacts. Add test for paths with spaces and overwrite protection.
5. `build [target]`: ensure/attach daemon, call `dag.run`, subscribe/poll for result with timeout, print concise status and gate summary. `--json` prints one JSON object to stdout; diagnostics go to stderr.
6. `doctor`: combine `atomcd /health`, `/schema` version, `daemon.status`, plugin availability and local tool probes (uv/ato/qmk/build123d/Renode) without requiring any optional hardware kernel to be installed. Distinguish `PASS`, `WARN`, `SKIP`, `FAIL`; exit non-zero only for required failures.
7. `plugin new <name> [--runtime ts|python|both]`: generate manifest/entrypoint/test scaffolds matching the frozen manifest schema and plugin SDK API; validate generated `atomc-plugin.json` with `@atomc/plugin-sdk` before writing. `plugin list` uses `plugins.list` and supports `--json`.
8. Vitest tests for command parsing/help, every implemented command via injected fakes, `--json` stdout discipline, exit codes, init safety/template copy, plugin scaffold validates, daemon errors/conflicts, missing plugins, timeout.
9. README with install/use/dev instructions and explicit current scope limitations.

## Definition of done
`pnpm --filter @atomc/cli test`, `typecheck`, `lint`, `build`; `pnpm exec biome check apps/atomc-cli`; package coverage ≥85%; `pnpm exec turbo run build test typecheck lint` passes after orchestrator adds root importer. Write handoff, conventional commits, push `wp/3.1-cli`. List exact root lock importer and any decisions needed.
