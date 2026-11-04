# WP-1.5 `docs-site` — handoff

## What was built

A complete VitePress 1.6 documentation site for atomc, deployed from `docs/` to GitHub Pages at
`https://dtmirizzi.github.io/atomc/`.

- **`docs/package.json`** — `@atomc/docs`, private, scripts `dev` / `build` / `preview` / `sync`;
  deps `vitepress: "catalog:"` and `vue ^3.5.44`.
- **`docs/.vitepress/config.ts`** — title/description, `base: "/atomc/"`, `cleanUrls`, `lastUpdated`,
  local search, edit-on-GitHub links, nav (Guide · Architecture · Reference · Plugins · Examples ·
  Plan · GitHub) and per-section sidebars, including a "Contracts (frozen)" group that renders the
  existing `docs/architecture/contracts/*.md` unchanged.
- **Content** (real prose, no lorem): `index.md` (hero + feature grid), `guide/` (install,
  first-build, converge), `architecture/` (overview, IR, DAG & gates, swarm, distribution, testing),
  `reference/` (IR schema browser, CLI + RPC placeholders, packages), `plugins/` (writing a plugin,
  manifest, conformance), `examples/` (atomc-pad, atomc-keeb), `plan/` (section index, status board,
  master plan). Future features are explicitly marked **planned** with the owning work package.
- **`docs/scripts/sync.mjs`** — idempotent, tolerant of missing sources:
  - copies `packages/core-ir/schema/system_ir.schema.json` → `docs/public/schema/` when present;
  - copies `PLAN.md` → `docs/plan/master.md` (gitignored) and generates `docs/plan/status.md` from
    §10; escapes raw `<tag>`-looking text so VitePress/Vue does not choke on plan snippets;
  - mirrors every `packages|plugins|apps/*/README.md` into `docs/reference/packages/` (link-rewritten
    to GitHub) plus an index.
- **Theme** `docs/.vitepress/theme/` extending the default theme, registering three components:
  - `SchemaBrowser.vue` — collapsible `$defs` tree with field/type/required/description and a filter
    box; fetches the generated schema and server-renders a contract-derived placeholder when it is
    absent.
  - `ModelViewer.vue` — lazy-loads the `<model-viewer>` web component from CDN for `.glb` artifacts,
    with a placeholder until Phase 4 produces them.
  - `GateBadge.vue` — PASS/FAIL/SKIP/ERROR badge.
- **`docs/public/favicon.svg`** and **`docs/.gitignore`** for generated inputs.
- **Pages enabled** on `dtmirizzi/atomc` with build type `workflow` (POST
  `repos/dtmirizzi/atomc/pages -f build_type=workflow`). WP-1.4's `docs.yml` will deploy to it.

## How to verify (exact commands)

```bash
# from repo root
pnpm install --frozen-lockfile
pnpm docs:build                       # runs sync + vitepress build; must exit 0

pnpm --filter @atomc/docs preview     # serves http://localhost:4173/atomc/
# check: /atomc/reference/ir-schema renders the schema tree; /atomc/plan/master? + /atomc/plan/status?

# TS/JS/Vue lint + format (markdown is excluded from this check; see open issues)
pnpm exec biome check docs/.vitepress/theme docs/.vitepress/config.ts docs/scripts docs/package.json
```

Individual pieces:

```bash
pnpm --filter @atomc/docs sync        # regenerate plan mirrors + schema copy + package READMEs
```

To exercise the "live" schema path, place a generated schema at
`packages/core-ir/schema/system_ir.schema.json` and re-run `sync`; the browser will fetch it and drop
the placeholder banner.

## Design decisions

- **Placeholder schema instead of a committed `public/schema`.** The real schema is owned by WP-1.1
  and is a generated artifact, so `docs/public/schema/` is gitignored and `sync` copies into it. To
  satisfy "the browser renders" before WP-1.1 lands, a contract-derived placeholder lives at
  `docs/.vitepress/theme/placeholder.schema.json` and is used as the in-code fallback (server-rendered
  first, then replaced by the fetched schema). This avoids shipping a fake "real" schema.
- **Rendered the frozen contracts in place.** They already sit under `docs/architecture/contracts/`,
  so they are VitePress pages with zero copying and zero edits to read-only files.
- **`BLOCK` on plan mirrors.** `master.md`/`status.md` are generated and gitignored; `PLAN.md` stays
  the single source of truth.
- **`<model-viewer>` via CDN** keeps the site build lean; the component degrades to a placeholder
  when no `src` is given or the CDN is unreachable.
- **`docs/.gitignore`** (owned path) instead of editing the orchestrator-owned root `.gitignore`.

## Deviations from contract

None. Node names, units, ID format, gate ids and RPC method names in the prose match
`docs/architecture/contracts/*` and `PLAN.md`. No contract files were edited.

## Open issues

- **`pnpm lint` (root) fails on Markdown, pre-existing.** Root `biome check .` applies the Markdown
  formatter and wants to re-pad every table in `PLAN.md`, `docs/plan/briefs/**` and
  `docs/architecture/contracts/**` — all orchestrator-owned and already red on `main`. The site's
  TS/JS/Vue paths are clean. This needs a root fix (see below) before `ci.yml` can be green.
- **WaveDrom** of a matrix scan / HID report (PLAN §7) is not implemented; the brief's component list
  only required `ModelViewer`, `SchemaBrowser` and `GateBadge`. Add in Phase 4 with real captures.
- **`vue` version** is declared explicitly in `docs/package.json` (`^3.5.44`) because it is not in the
  pnpm catalog.
- Docs deploy depends on WP-1.4's `.github/workflows/docs.yml`; Pages is enabled and waiting for it.

## Root changes needed

1. **`biome.json`** — stop formatting Markdown (or add `!**/*.md` to `files.includes`, or enable
   `vcs.useIgnoreFile`), otherwise root `biome check .` fails on `PLAN.md`, the briefs and the
   contracts. Verify with `pnpm exec biome check .`.
2. **`pnpm-workspace.yaml`** — optionally add `vue: ^3.5.44` to the catalog so `docs/package.json` can
   use `"catalog:"` like every other dep.
3. **`turbo.json`** — the `build` task caches `dist/**`; VitePress writes to `docs/.vitepress/dist`.
   Add that output (and a `typecheck`-less docs entry is fine) if docs build caching is wanted.
4. **`.github/workflows/docs.yml`** (WP-1.4) — deploy `docs/.vitepress/dist` to Pages with
   `actions/deploy-pages`; Pages is already enabled with `build_type=workflow`.
