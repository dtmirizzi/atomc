# WP-1.4 `ci-release` — GitHub Actions, release pipelines, Docker

Read `_common.md` first. Read PLAN §5 (distribution) and §6 (testing) carefully.
**Exception to root ownership: you own `.github/**` and `docker/**`.**

## Owned paths
`.github/workflows/**`, `.github/ISSUE_TEMPLATE/**`, `.github/PULL_REQUEST_TEMPLATE.md`,
`docker/**`, `scripts/release/**`, `CONTRIBUTING.md`, `SECURITY.md`.

## Deliverables
1. `ci.yml` — on PR + push main. Jobs: `lint` (biome, ruff, ruff format --check), `typecheck`
   (mypy, tsc via turbo), `test-py` (matrix ubuntu-latest, macos-latest; `astral-sh/setup-uv`, py 3.14,
   `uv sync --all-packages`, pytest w/ coverage, upload artifact), `test-ts` (matrix node 22, 25;
   `pnpm/action-setup`, `actions/setup-node` cache pnpm, `turbo run build test`), `contract`
   (`turbo run contract` + `python -m atomc_core_ir.schema --check` + TS `gen --check`), `docs`
   (`pnpm docs:build`). Jobs must no-op gracefully when a package doesn't exist yet (e.g. guard with
   `hashFiles`), because Phase 1 lands incrementally. Concurrency group cancels superseded runs.
   Pin actions by major version tag (latest majors).
2. `docs.yml` — build VitePress (`pnpm docs:build`, output `docs/.vitepress/dist`) and deploy with
   `actions/upload-pages-artifact` + `actions/deploy-pages` on push to main; `permissions: pages: write, id-token: write`.
3. `release-npm.yml` — on tag `v*` or `workflow_dispatch(dry_run)`: changesets version check,
   `pnpm -r publish --access public --provenance` (dry_run → `--dry-run`). Needs `NPM_TOKEN` secret;
   document in handoff.
4. `release-pypi.yml` — on tag `v*` / dispatch(dry_run): `uv build --all-packages`, publish with
   `pypa/gh-action-pypi-publish` via **Trusted Publishing** (environment `pypi`); dry_run → TestPyPI or
   skip publish. Document the one-time PyPI trusted publisher setup steps for the user.
5. `scripts/release/sync-versions.py` — reads the version from root `package.json`... no: from
   `.changeset`-bumped `packages/core-ir/ts/package.json` (or a `VERSION` file you create under
   `scripts/release/VERSION`) and writes it into every `*/python/pyproject.toml`. Lock-step versions (PLAN §5.2). Include a `--check` mode.
6. `docker/Dockerfile` — multi-stage: `base` (debian bookworm-slim + uv + node 22 + pnpm), `kernels`
   (Renode 1.17.0 linux portable, arm-none-eabi-gcc, QMK CLI, python 3.14 venv w/ build123d/OCP),
   `atomc` (copies repo, `uv sync`, `pnpm install --frozen-lockfile`, `pnpm build`). Plus `docker.yml`
   to build on PR (no push) and push to `ghcr.io/dtmirizzi/atomc` on tag. Keep `atomc` stage tolerant
   of packages not existing yet.
7. `nightly-hw.yml` — scheduled; runs `scripts/doctor.py` + e2e placeholders inside the Docker image.
8. `CONTRIBUTING.md` (dev setup = `scripts/bootstrap.sh`, workflow, conventional commits, changesets),
   `SECURITY.md`, PR template (checklist mirrors definition of done), issue templates (bug, feature, plugin idea).

## Verification
`actionlint` (install via `brew install actionlint`) passes on all workflows. `docker build --target base`
succeeds locally (full image build optional — note time). Open a draft PR from your branch with
`gh pr create --draft` and report the CI result link in your handoff (failures due to missing
packages are OK only if jobs skip, not fail).
