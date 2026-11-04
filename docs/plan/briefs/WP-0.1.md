# WP-0.1 `bootstrap` — Environment installation & verification

## Role
You are the environment engineer for the `atomc` monorepo. Your job is to install every external
toolchain the project needs on this macOS arm64 machine, make the installation reproducible, and
produce a doctor script that proves it works. Read `PLAN.md` §0 (decisions), §2 (version matrix),
and §8 Phase 0 first.

## Owned paths (exclusive)
- `scripts/bootstrap.sh`
- `scripts/doctor.py`
- `docs/plan/ENVIRONMENT.md`
- `.python-version`
- `.tool-versions` (optional)

Do not edit anything else. Do not create the uv/pnpm workspace files (`pyproject.toml`,
`pnpm-workspace.yaml`); the orchestrator owns those. You may create a throwaway `.venv/` at repo
root for verification; it is gitignored.

## Deliverables
1. `scripts/bootstrap.sh` — idempotent, `set -euo pipefail`, logs each step, skips already-satisfied
   steps, works from a fresh clone. Installs (latest stable; pin exact versions you observe):
   - `uv python install 3.14` and write `.python-version` = `3.14`
   - `uv tool install atopile==0.15.9` (requires py3.14) → `ato` on PATH
   - Homebrew: `dotnet@8` (pyrenode3 coreclr runtime), `cmake`, `ninja`, cask `gcc-arm-embedded`
   - Renode 1.17.0 `osx-arm64-portable` from GitHub releases → install under `~/.local/opt/renode-1.17.0`,
     symlink `~/.local/bin/renode`, clear quarantine (`xattr -dr com.apple.quarantine`)
   - Node side: verify `node >= 22`, `pnpm >= 10`; `pnpm add -g turbo@latest @biomejs/biome@latest`
   - A verification venv: `uv venv --python 3.14 .venv && uv pip install --python .venv/bin/python
     "build123d==0.13.0" "cadquery-ocp" kiutils trimesh pydantic
     "pyrenode3 @ git+https://github.com/antmicro/pyrenode3"`
   - Optional flag `--with-kicad` → `brew install --cask kicad` (do NOT run by default; GUI app)
   - Exports needed env (`PYRENODE_RUNTIME=coreclr`, `PYRENODE_BIN` or `PYRENODE_PKG`) into
     `~/.atomc/env.sh` and prints instructions to source it.
2. `scripts/doctor.py` — stdlib-only Python 3.14 script, exit 0 iff all checks pass, `--json` output.
   Checks: uv, python 3.14, pnpm, node, ato (`ato --version`), arm-none-eabi-gcc, cmake, ninja,
   dotnet 8, renode (`renode --version` headless), `import build123d, OCP` in `.venv`,
   `from pyrenode3.wrappers import Emulation` in `.venv` (with the env sourced), `import kiutils`,
   `gh auth status`. Each check prints name, found version, PASS/FAIL, and a fix hint.
3. **Functional smoke proofs** (document in ENVIRONMENT.md with exact commands + output excerpts):
   - `ato create project` scratch project in `/tmp`, `ato build` succeeds.
   - build123d: generate a 50×30×1.6 mm box with one 1 mm hole, export `.step`, assert file > 1 KB.
   - Renode headless: run a built-in STM32 demo script (e.g. `scripts/single-node/stm32f4_discovery.resc`
     or any STM32G4 platform in `platforms/`) with `--disable-xwt --console`, `start`, wait 2 s,
     `quit`; capture that it ran. Also prove `pyrenode3` can create an `Emulation()` and load a
     `platforms/cpus/stm32g4*.repl`. If pyrenode3 cannot work on macOS, document precisely why and
     prove the fallback (Renode telnet monitor on port 1234 or `renode-test` Robot runner) instead.
   - arm-none-eabi-gcc compiles a trivial `main.c` for `-mcpu=cortex-m4 -mthumb`.
4. `docs/plan/ENVIRONMENT.md` — exact versions installed, paths, env vars, workarounds, time taken,
   and anything that blocks later phases.

## Definition of done
- `bash scripts/bootstrap.sh` twice in a row: second run completes in < 30 s with every step "skipped".
- `python3 scripts/doctor.py` exits 0 (KiCad check reports SKIP unless installed).
- All four smoke proofs recorded in ENVIRONMENT.md.
- Commits on branch `wp/0.1-bootstrap` using conventional commits; a `HANDOFF.md` at
  `docs/plan/handoffs/WP-0.1.md` with: what was done, how to re-verify, open issues, and any
  "root changes needed" for the orchestrator.

## Constraints
- Use latest stable versions; record the exact versions you see.
- Never `sudo`. Never modify shell rc files; write to `~/.atomc/env.sh` and tell the user.
- No force-push. Small commits.
- If a download needs credentials, a GUI, or a license click, stop and ask the orchestrator.
- If Homebrew is missing a formula, stop and ask rather than building from source.

## Stop and ask when
- Renode 1.17.0 arm64 dmg fails Gatekeeper or needs a different install path.
- pyrenode3 + pythonnet + dotnet 8 cannot import after two honest attempts (report the error).
- atopile 0.15.9 refuses to install on 3.14 (report `uv` resolution error).
