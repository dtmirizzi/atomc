# WP-5.5 `cli-quote-orders` — real `atomc quote` and `atomc orders` UX

Read `_common.md`, PLAN §§1, 4, 6, 8, 9; `apps/atomc-cli/**` (the capability-stub pattern for `quote`/`orders` — see `src/commands/capability.ts` and `sim`/`jig` wiring); the WP-5.3/5.4 handoffs and their plugins (the tools/gates you drive); the WP-3.1 CLI handoff. `atomc quote` and `atomc orders` currently exit 3 as honest stubs — this package makes them real by calling the daemon, with the same no-fake-PASS rules as `atomc build`.

## Owned paths
- `apps/atomc-cli/src/commands/quote.ts`, `apps/atomc-cli/src/commands/orders.ts`
- `apps/atomc-cli/src/program.ts` (wire the two commands; minimal edits)
- `apps/atomc-cli/test/quote.test.ts`, `apps/atomc-cli/test/orders.test.ts`
- `apps/atomc-cli/README.md` (status table rows + scope notes)
- `docs/reference/cli.md` (command rows)
- `docs/plan/handoffs/WP-5.5.md`

Do not edit the plugins, daemon, Studio or root files.

## Deliverables
1. `atomc quote [--json] [--refresh]`: start/attach the daemon (existing `ensureDaemon` pattern), call the sourcing plugin's `fab.quote_pcb` tool via the daemon's tool-invocation RPC (study how `plugin list`/`converge` invoke tools; use the client's tool call surface), then read `/fabrication/quotes` and print per-fab quotes (total, lead time, breakdown) with the `fab.quote_under_budget` gate status. Without plugins loaded → structured `unavailable` (exit 3), never a fake quote.
2. `atomc orders [--json] [--status <s>]`: read `/orders` from the daemon and print the ledger as a table (id, vendor, kind, status, total, tracking summary) with status filtering; `atomc orders build-cart [--vendor <v>] [--out <dir>]` calls `build_cart` and prints the written file paths. No mutations beyond the explicitly-named `build-cart`.
3. Honest exits: 0 = data read and gates green; 1 = data read but blocking gate failed or no data exists for the project; 3 = daemon/plugins unavailable. Same `--json` single-object contract as every command.
4. Tests: extend the CLI fake-`DaemonApi` harness — quote (with quotes + gate PASS/FAIL, empty fabrication, plugin-missing unavailable), orders (ledger rendering, status filter, build-cart file outputs, empty ledger), option validation, exit codes. No real daemon in unit tests.
5. Handoff: exact commands, the RPC surface used, deviations, root changes needed (should be none).

## Definition of done
- `pnpm --filter @atomc/cli test`, `typecheck`, `lint`, `build` pass; coverage floors hold.
- Both commands' outputs trace to daemon reads; every unavailable path is structured and honest.
- Conventional commits; push `wp/5.5-cli-quote-orders`; do not merge.

## Stop and ask
If the daemon's tool-invocation RPC cannot call a plugin tool with arguments (contract gap), stop and report the exact method instead of driving plugins directly.
