# Install

::: info Current status
The CLI and project scaffolding are implemented in this checkout but are not published to npm. For development, use the repository bootstrap script; published one-command installation and automatic daemon/plugin installation remain future release work.
:::

## Requirements

| Tool              | Version                | Notes                                                  |
| ----------------- | ---------------------- | ------------------------------------------------------ |
| Python            | 3.14.x                 | pinned by `uv`; atopile 0.15.9 requires `>=3.14,<3.15` |
| Node              | 25 (≥22 LTS supported) | uses `pnpm` 10 workspaces + `turbo` 2                  |
| uv                | latest                 | Python interpreter + tool management                   |
| pnpm              | 10                     | TypeScript workspaces                                  |
| Renode            | 1.17.0                 | osx-arm64 portable; Docker fallback + CI               |
| .NET runtime      | 8 LTS                  | required by `pyrenode3` (coreclr)                      |
| arm-none-eabi-gcc | latest                 | QMK firmware builds                                    |
| cmake, ninja      | latest                 | native builds                                          |
| QMK CLI           | latest                 | `uv tool install qmk`                                  |

KiCad 9.x is optional and only needed to view or hand-edit layouts.

## Bootstrap from a checkout

```bash
git clone https://github.com/dtmirizzi/atomc
cd atomc
./scripts/bootstrap.sh   # idempotent; no-ops on a second run
uv run python scripts/doctor.py   # exits 0 when everything is present
```

`scripts/bootstrap.sh` installs the Python 3.14 interpreter, the atopile and QMK tools, the Renode
portable, the .NET runtime, the ARM toolchain, and the Python kernels (`build123d`, `OCP`, `kiutils`,
`trimesh`, `pyrenode3`). `scripts/doctor.py` re-checks every version and prints any workarounds that
were needed (for example the `PYRENODE_RUNTIME=coreclr` and `PYRENODE_BIN` environment variables, or
macOS Gatekeeper quarantine on the Renode `.dmg`).

## JavaScript workspaces

```bash
pnpm install
pnpm build
```

## Local source workflow

```bash
pnpm --filter @atomc/cli build
node apps/atomc-cli/dist/index.js init my-board
node apps/atomc-cli/dist/index.js doctor
```

These commands run the source build. The CLI does not install daemon/plugins automatically and the package has not been published. The planned distribution channels are in
[Distribution](/architecture/distribution).
