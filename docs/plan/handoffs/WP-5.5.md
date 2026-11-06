# WP-5.5 `cli-quote-orders` — handoff

Branch `wp/5.5-cli-quote-orders` · package `apps/atomc-cli` (`@atomc/cli`). Makes `atomc quote` and
`atomc orders` real: they attach to the daemon, drive the WP-5.3/5.4 plugins over the frozen
`tools.call` RPC, read the resulting IR, and report honest exit codes. No price, cart or order is
ever invented.

## What was built

1. **`atomc quote [--refresh] [--project <dir>] [--json]`** (`src/commands/quote.ts`)
   - `ensureDaemon(projectRoot)` → `plugins.list` → requires the loaded `sourcing` plugin.
   - Calls `tools.call {plugin:"sourcing", tool:"quote_pcb", args:{write:true, force?}}`, then reads
     `/fabrication/quotes` from `ir.get("/")` (falls back to the tool's `quotes` payload when the IR
     read fails), then runs `gates.run ["gate:fab.quote_under_budget"]`.
   - Prints per-fab quotes (total, lead time, breakdown) and the gate status.
   - Exits `0` only when quotes exist **and** the gate is `PASS`; `1` when no quotes or the gate is
     FAIL/SKIP/ERROR; `3` when the daemon/plugin is unavailable or `quote_pcb` reports
     `UNAVAILABLE`/`ERROR`.
2. **`atomc orders [--status <s>] [--project <dir>] [--json]`** (`src/commands/orders.ts`, wired as
   the default `list` subcommand) — read-only. Reads `/orders` via `ir.get("/")`, renders a table
   (`id, vendor, kind, status, total, tracking summary`) with an optional status filter. Exits `0`
   when records exist, `1` for an empty ledger, `2` for an invalid `--status`, `3` when unavailable.
3. **`atomc orders build-cart [--vendor <v>] [--out <dir>] [--project <dir>] [--json]`** — calls
   `tools.call {plugin:"orders", tool:"build_cart", args:{}}` and prints the artifacts the plugin
   wrote (plus draft order ids and the DRAFT-only notice). `--vendor` filters the reported artifacts;
   `--out` copies the produced files into a client-side directory. Exits `1` on a tool `FAIL`, `3`
   when the tool call or daemon is unavailable.
4. **Honest exits + single-object `--json`** matching the other commands; all human text goes to
   stderr, exactly one JSON object to stdout.
5. **Tests** (`test/quote.test.ts`, `test/orders.test.ts`, 108 total in the package): quote
   success/PASS, gate FAIL, `--refresh` force, empty fabrication, tool `UNAVAILABLE`/`ERROR`, missing
   status, malformed quotes, non-array node, fallback, plugin-missing/daemon-unavailable/RPC-failure;
   orders ledger render, status filter, filter-empty vs empty-ledger, invalid status, malformed
   entries, build-cart success/`--vendor`/`--out` copy/copy-failure/`FAIL`/no-match/malformed
   artifacts, plugin-missing/RPC-failure. No real daemon, network or hardware.
6. **Docs**: `apps/atomc-cli/README.md` status table/scope notes and `docs/reference/cli.md` command
   rows updated.

## RPC surface used

- `plugins.list` → gate on `sourcing` / `orders` being loaded.
- `tools.call {plugin, tool, args}` → `sourcing.quote_pcb` (manifest name; brief calls it
  `fab.quote_pcb`), `orders.build_cart`.
- `ir.get {path:"/"}` → extract `/fabrication/quotes` and `/orders.orders`.
- `gates.run {ids:["gate:fab.quote_under_budget"]}` for the quote gate.
- `daemon-client` `ensureDaemon` / `close` as everywhere else.

## How to verify (exact commands)

```bash
# from the worktree root (workspace deps must be built first)
pnpm install --frozen-lockfile
pnpm --filter @atomc/core-ir build
pnpm --filter @atomc/plugin-sdk build
pnpm --filter @atomc/daemon-client build
pnpm --filter @atomc/cli build
pnpm --filter @atomc/cli test            # 108 passed, 10 files
pnpm --filter @atomc/cli test:coverage   # 96.7% stmts / 88.07% branches / 99.03% lines (floors 85)
pnpm --filter @atomc/cli typecheck
pnpm --filter @atomc/cli lint
pnpm exec biome check apps/atomc-cli/src/commands/quote.ts apps/atomc-cli/src/commands/orders.ts \
  apps/atomc-cli/src/program.ts apps/atomc-cli/test/quote.test.ts apps/atomc-cli/test/orders.test.ts \
  apps/atomc-cli/test/helpers/fakes.ts apps/atomc-cli/README.md docs/reference/cli.md
# delete apps/atomc-cli/coverage before a direct biome run
```

Real daemon smoke (optional, uses the Phase-5 plugins): `atomc build`, then `atomc quote` and
`atomc orders` on `examples/atomc-pad`; `atomc orders build-cart` after a sourcing run. Without
vendor credentials/JLCPCB keys, `quote` correctly exits `3` (`quote_pcb` → `UNAVAILABLE`) rather than
inventing a price.

## Design decisions

- **Read the IR root and extract nodes.** `ir.get` on an absent node is reported as `-32602`
  (the daemon maps `MissingNodeError`, a `ValueError`, to invalid-params), which is indistinguishable
  from a genuine parameter error. Reading `/` avoids that ambiguity and is cheap for a CLI.
- **Gate freshness.** After `quote_pcb` writes `/fabrication`, `gates.list` may hold a stale result,
  so the command calls `gates.run` for `gate:fab.quote_under_budget`. A failed gate run degrades to a
  null gate and exit `1`, never a fake pass.
- **`orders` is a default `list` subcommand.** Commander 15 lets a parent and child both declare
  `--json`, but the child silently loses the flag when the parent also declares it. Making `list`
  the default subcommand keeps `atomc orders --json` working while allowing
  `atomc orders build-cart --json`.
- **`--vendor` / `--out` are client-side.** The WP-5.4 `build_cart` schema has no `vendor`/`out_dir`
  argument (and `artifact_root` is fixed by the daemon), so the CLI filters the reported artifacts by
  vendor and copies the produced files into `--out` itself. This keeps `build_cart` unchanged and is
  honest about where files originate.

## Deviations from contract (should be none)

- **Files touched beyond the literal owned list (deliverable required it):**
  `apps/atomc-cli/test/helpers/fakes.ts` was extended with `ir`, `irByPath`, `toolResults`,
  `gateRuns`, `requestResults` options plus `listPluginsThrows`/`getIRThrows`/`gatesRunThrows` and a
  `toolCalls` recorder, to drive the new commands. No other WP owns the CLI, so this is conflict-free.
- **Exit code `2`** is used for an invalid `--status` (matching `converge`'s option validation);
  the brief only fixed `0/1/3`.
- The brief names the tool `fab.quote_pcb`; the manifest tool name is `quote_pcb` (the `fab` prefix
  is the Python module). The CLI calls `sourcing.quote_pcb`.

## Open issues

- `build_cart` artifact paths are daemon-host paths; `--out` copies them client-side and fails with
  an honest `1` if they are not readable locally (e.g. a remote daemon).
- `--refresh` passes `force:true`, but the shipping `FabService` has no cache, so it is currently a
  no-op accepted for tool-schema stability.
- The CLI has no typed `runGates`/`callTool` wrapper, so the two commands use the generic
  `client.request`; a future WP could add typed methods to `DaemonApi`.

## Root changes needed

- None. No new dependency; no root config or lockfile change.
