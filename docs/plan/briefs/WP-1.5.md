# WP-1.5 `docs-site` — VitePress site + GitHub Pages

Read `_common.md` first, then PLAN §7.

## Owned paths
`docs/**` **except** `docs/plan/briefs/**`, `docs/plan/handoffs/**` (other agents') and
`docs/architecture/contracts/**` (read-only, but you render them). You also own `docs/package.json`.

## Deliverables
1. `docs/package.json` → name `@atomc/docs`, private, scripts `dev`, `build`, `preview`, `sync`;
   deps `vitepress: "catalog:"`, `vue` (latest). Already listed in `pnpm-workspace.yaml`.
2. `docs/.vitepress/config.ts`: title "atomc", description, `base: "/atomc/"` (GitHub Pages project
   site https://dtmirizzi.github.io/atomc/), clean URLs, local search, edit-on-GitHub links, nav:
   Guide · Architecture · Reference · Plugins · Examples · Plan · GitHub. Sidebars for each.
3. Pages (real content, not lorem): `index.md` (hero + feature grid explaining the
   circuits→firmware→enclosure/jig→supply-chain story and the keyboard example), `guide/` (install
   via bootstrap.sh / future `npx @atomc/cli init`, first build, converge — mark future features
   "planned"), `architecture/` (overview diagram from PLAN §1, IR, DAG & gates, swarm harness,
   distribution, testing model; include the existing `contracts/*.md` in a sidebar group),
   `reference/` (IR schema browser page, CLI & RPC placeholders), `plugins/` (writing a plugin,
   manifest contract), `examples/` (atomc-pad, atomc-keeb — planned), `plan/` (renders PLAN.md via
   include + a status page).
4. `docs/scripts/sync.mjs` (`pnpm --filter @atomc/docs sync`, also run before build): copies
   `packages/core-ir/schema/system_ir.schema.json` → `docs/public/schema/system_ir.schema.json` if it
   exists (fine if missing → page shows "schema not built yet"), copies `PLAN.md` → `docs/plan/master.md`
   (generated, gitignored) and package READMEs into `docs/reference/packages/`.
5. Vue components in `docs/.vitepress/theme/`: `SchemaBrowser.vue` (fetches the schema JSON, renders
   collapsible tree of $defs with field, type, required, description; search box), `ModelViewer.vue`
   (wraps `<model-viewer>` web component loaded from CDN for `.glb` files, placeholder until Phase 4),
   `GateBadge.vue`. Register in a custom theme extending the default.
6. Enable Pages on the repo with build type "workflow":
   `gh api -X POST repos/dtmirizzi/atomc/pages -f build_type=workflow` (if it already exists use PUT).
   WP-1.4 writes the deploy workflow; you just make sure `pnpm docs:build` works from repo root.

## Definition of done
From repo root: `pnpm install && pnpm docs:build` green; `pnpm --filter @atomc/docs preview` serves
and the schema browser renders using a copy of a schema (use WP-1.1's when it appears on
`origin/wp/1.1-core-ir-py`, otherwise a stub). No dead internal links (VitePress fails build on dead
links — keep that on). Handoff + push.
