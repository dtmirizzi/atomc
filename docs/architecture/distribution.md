# Distribution

atomc ships in several forms, all versioned on a **single `0.x.y` line** so the CLI, daemon, plugins
and IR are always lock-stepped.

## Artifacts

| Artifact | Channel | Consumer |
| -------- | ------- | -------- |
| `atomc` (CLI) | npm `@atomc/cli` (+ `npx @atomc/cli`), plus a single-file bundle on GitHub Releases | end users |
| `atomcd` (daemon) | PyPI `atomc-daemon` (+ `uvx atomc-daemon`), auto-installed by the CLI into `~/.atomc/venv` via `uv` on first run | CLI |
| `atomc-core-ir` | PyPI + npm `@atomc/core-ir` (same version number) | plugins, daemon, harness |
| `@atomc/plugin-sdk` + `atomc-plugin-sdk` | npm + PyPI | third parties |
| Built-in plugins | PyPI `atomc-plugin-*` + npm `@atomc/plugin-*` | bundled into the `atomc` meta-package |
| `atomc` meta | PyPI `atomc[all]` extras | `uv tool install atomc[all]` |
| Docker | `ghcr.io/dtmirizzi/atomc:<ver>` (Linux, includes Renode, arm-gcc, KiCad-cli) and `atomc:slim` | CI, Linux, hermetic builds |
| Homebrew | `dtmirizzi/tap/atomc` (Phase 5+) | macOS |
| Docs | GitHub Pages | everyone |

## Versioning & release

- One version line across the monorepo (`0.x.y`). `changesets` drives the TS changelog; a sync script
  mirrors the version onto the Python packages with `uv version`.
- Tagging `v0.x.y` triggers:
  - `release-npm.yml` — `pnpm publish` with provenance,
  - `release-pypi.yml` — `uv build` + Trusted Publishing (OIDC),
  - a GHCR image push, and
  - a GitHub Release with the CLI bundle and example artifacts (`atomc-keeb.step`, `.glb`, `.repl`).
- Every merge to `main` publishes a `0.x.y-next.<sha>` pre-release to npm `next` and TestPyPI.

## Install UX target

```bash
npx @atomc/cli init my-board       # bootstraps uv venv, installs atomcd + plugins, runs doctor
atomc build                        # starts/attaches daemon, runs DAG
atomc converge                     # swarm until gates PASS
```

`atomc doctor` verifies that the CLI, daemon and plugin versions agree, and that Renode, OCP and the
ARM toolchain are present. Release automation is owned by WP-1.4
(`.github/workflows/{ci,release-npm,release-pypi,docs,nightly-hw}.yml`).
