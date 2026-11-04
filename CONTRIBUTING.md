# Contributing to atomc

Thanks for helping build `atomc`. This document covers local setup, the workflow we
expect on pull requests, and the release/versioning rules.

## Development setup

The one-shot, idempotent installer is `scripts/bootstrap.sh` (introduced in WP-0.1).
It installs and verifies every toolchain: `uv` + Python 3.14, Node 22+/pnpm 10,
Renode 1.17.0, `arm-none-eabi-gcc`, build123d/OCP, QMK, and (optionally) KiCad.

```bash
git clone https://github.com/dtmirizzi/atomc.git
cd atomc
bash scripts/bootstrap.sh     # safe to re-run; skips what is already present
source ~/.atomc/env.sh        # PYRENODE_*, QMK_HOME, ...
python3 scripts/doctor.py     # exit 0 == environment is good
```

Then install the workspace dependencies:

```bash
uv sync --all-packages        # Python workspace
pnpm install --frozen-lockfile # TypeScript workspace
```

If `scripts/bootstrap.sh` does not exist yet, the environment work package (WP-0.1)
has not landed — see `docs/plan/ENVIRONMENT.md` for the manual steps.

## Repository layout

```
packages/*/python/   Python distributions (src/ layout, hatchling)
packages/*/ts/       TypeScript packages  (ESM, tsup, vitest)
plugins/*/           Built-in plugins (optional python/ + ts/)
apps/                CLI and Studio
docs/                VitePress site → GitHub Pages
scripts/             bootstrap, doctor, release helpers
docker/              multi-stage image
```

Every Python distribution lives at `<pkg>/python/`; every TS package at
`<pkg>/ts/` and extends `tsconfig.base.json`. Root config files
(`pyproject.toml`, `package.json`, `pnpm-workspace.yaml`, `turbo.json`,
`biome.json`, `tsconfig.base.json`) are maintained by the orchestrator; ask in your
PR if you need a change there.

## Workflow

1. Branch from `main`: `git switch -c feat/short-description`.
2. Make small, focused commits using **Conventional Commits**
   (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`). Example:
   `feat(core-ir): validate net references on load`.
3. Keep the tree green (see "Definition of done" below).
4. Add a changeset for user-visible changes:
   ```bash
   pnpm changeset
   ```
5. Open a PR, fill in the checklist, and request review. Never force-push.

## Definition of done (run these before requesting review)

```bash
# Python — only if your change touches a */python/ package
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy

# TypeScript — only if your change touches a */ts/ package
pnpm --filter <pkg> typecheck
pnpm --filter <pkg> test
pnpm exec biome check <your paths>

# Cross-language contract work
pnpm exec turbo run contract
```

CI (`.github/workflows/ci.yml`) runs the same checks on Linux and macOS, with Node
22 and 25. A red CI run must be fixed before merge; jobs that find no packages
skip gracefully during incremental Phase 1 work.

## Versioning & releases (single version line)

`atomc` versions the whole monorepo together (`0.x.y`). The single source of truth
is [`scripts/release/VERSION`](./scripts/release/VERSION); `scripts/release/sync-versions.py`
mirrors it into every `*/python/pyproject.toml` and every `@atomc/*` `package.json`.

- **Do not** hand-edit package versions. To raise the version:
  `echo 0.2.0 > scripts/release/VERSION && python3 scripts/release/sync-versions.py`.
- Verify lock-step (used in CI and on release):
  `python3 scripts/release/sync-versions.py --check`.
- Push a `v<version>` tag to trigger `release-npm.yml` (pnpm publish with
  provenance) and `release-pypi.yml` (Trusted Publishing/OIDC). The tag must match
  `scripts/release/VERSION`.
- Manual runs of both release workflows default to `dry_run=true`.

## Reporting security issues

Please do **not** open a public issue for security problems — see
[SECURITY.md](./SECURITY.md).
