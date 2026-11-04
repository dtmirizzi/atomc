# Common rules for every atomc sub-agent (read this first)

- You are a sub-agent managed by an orchestrator. You work in your own git worktree on branch
  `wp/<id>-<slug>`. Start with `git pull --rebase origin main`.
- Read `PLAN.md` (esp. §0 decisions, §2 versions, §4 contracts, §6 testing, §9 ownership rules) and
  the contract docs in `docs/architecture/contracts/` that your brief cites.
- **Only edit your owned paths.** Root files (`pyproject.toml`, `package.json`, `pnpm-workspace.yaml`,
  `turbo.json`, `biome.json`, `tsconfig.base.json`, `.github/**` unless you are WP-1.4) are
  orchestrator-owned. If you need a root change, list it under "Root changes needed" in your handoff
  and work around it locally (do NOT edit).
- Use latest stable versions. TS deps: use `"catalog:"` for anything in the pnpm catalog. Python deps:
  `>=` the version in PLAN §2.
- Python 3.14 via `uv` (`uv run`, `uv sync`). Python packages live at `<pkg>/python/` with a `src/` layout
  and `hatchling` build backend. TS packages live at `<pkg>/ts/` (ESM, `"type": "module"`, tsup build,
  vitest tests, extends `../../../tsconfig.base.json`).
- Conventional commits, small commits. Never force-push. Never `sudo`.
- Must stay green before you report done: your package's tests, `uv run ruff check`, `uv run ruff format --check`,
  `uv run mypy` (Py) / `pnpm --filter <pkg> typecheck`, `pnpm exec biome check <your paths>` (TS).
- When done: write `docs/plan/handoffs/WP-<id>.md` (What was built · How to verify (exact commands) ·
  Design decisions · Deviations from contract (should be none) · Open issues · Root changes needed),
  commit, `git push -u origin <branch>`, then reply with a 5-line summary.
- **Stop and ask** (reply with a question and wait) when: a contract is ambiguous or seems wrong,
  you need a dependency not in PLAN §2, you need credentials/GUI, or you're blocked > 15 min.
