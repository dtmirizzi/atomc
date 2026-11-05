# WP-0.1 `bootstrap` — Handoff

Branch: `wp/0.1-bootstrap` · Status: **done** · Date: 2026-11-04

Full environment record (versions, paths, workarounds, smoke-proof transcripts):
[`docs/plan/ENVIRONMENT.md`](../ENVIRONMENT.md).

## What was done

Everything in the WP-0.1 brief is installed, verified, and reproducible. Deliverables:

| File | Purpose |
|------|---------|
| `scripts/bootstrap.sh` | idempotent, `set -euo pipefail`, no sudo; installs all toolchains; writes `~/.atomc/env.sh` |
| `scripts/doctor.py` | stdlib-only py3.14 doctor; 23 checks; `--json`; exit 0 iff all pass |
| `docs/plan/ENVIRONMENT.md` | exact versions, paths, env vars, workarounds, timing, the five smoke proofs |
| `.python-version` | `3.14` |

Installed (exact versions in ENVIRONMENT.md §1): uv 0.9.8 + standalone copy in `~/.local/bin`;
CPython 3.14.0; atopile 0.15.9 (`ato`); dotnet@8 8.0.133; cmake 4.4.5; ninja 1.13.2; Renode 1.17.0
(`~/.local/opt/renode-1.17.0`, `renode` on PATH); node 25.1.0 / pnpm 10.30.3 / turbo 2.11.10 /
biome 2.6.5; QMK CLI 1.2.0 + `~/qmk_firmware` @ `f5db962110`; verification venv with build123d
0.13.0, cadquery-ocp 8.0.1.1.0, kiutils 1.4.8, trimesh 5.2.0, pydantic 2.14.2, pyrenode3
(git `27362def`) + pythonnet 3.2.1. KiCad intentionally not installed (optional, `--with-kicad`).

## Definition of done — evidence

- `bash scripts/bootstrap.sh` twice: second run **~7 s**, all 19 steps `skip` (required < 30 s). ✅
- `python3 scripts/doctor.py` → exit **0**, all checks PASS (KiCad SKIP, as allowed). `--json` ok. ✅
- Five smoke proofs recorded in ENVIRONMENT.md:
  1. atopile create + build scratch project → `Build successful! 🚀` ✅
  2. build123d 50×30×1.6 box + 1 mm hole → `.step` 20,282 bytes (> 1 KB) ✅
  3. Renode headless `stm32f4_discovery.resc` (Contiki boots on `uart4`) **and** pyrenode3
     `Emulation()` + `load_repl("platforms/cpus/stm32f4.repl")` + start/pause ✅
  4. `arm-none-eabi-gcc` Cortex-M4 compile + link with `nosys`/`nano` specs ✅
  5. `qmk compile -kb handwired/onekey/blackpill_f411 -km default` ✅, then boot the `.elf` in
     Renode on `stm32f412.repl` for 2 s emulated time → **no HardFault** (warnings only; no UART
     banner because the stock keymap has no console) ✅

## How to re-verify

```bash
bash scripts/bootstrap.sh          # idempotent; second run < 30 s, all skips
. ~/.atomc/env.sh                  # required for Renode / pyrenode3 / QMK / arm toolchain
python3 scripts/doctor.py          # exit 0
python3 scripts/doctor.py --json
```

Smoke proofs are reproduced command-by-command in `docs/plan/ENVIRONMENT.md` §4.

## Deviations from the brief (all forced, all documented)

1. **`gcc-arm-embedded` cask → Homebrew formulae.** The cask runs a `.pkg` via `sudo`, which cannot
   prompt in a non-interactive session. Per the orchestrator's instruction we never used sudo. We
   install homebrew/core `arm-none-eabi-gcc` (16.2.0) **and** `osx-cross/arm/arm-gcc-bin@13`
   (keg-only). The core formula **lacks `nosys.specs`/`nano.specs`**, so QMK's compiler probe fails
   with it; the full `arm-gcc-bin@13` toolchain (13.2.1) is what `env.sh` puts first and what QMK
   uses.
2. **Extra AVR deps.** `qmk doctor` also requires `avr-gcc`, `avrdude`, `dfu-programmer`,
   `dfu-util`, `dos2unix`. They are unused by the STM32F411 target but were installed (formulae only,
   `osx-cross/avr` tap for `avr-gcc@9`) so `qmk doctor` passes cleanly.
3. **Renode smoke uses STM32F4, not STM32G4.** Renode 1.17.0 ships no `stm32g4*.repl`; the F4 family
   is present and is the family the example uses.
4. **pyrenode3 env var is `PYRENODE_PATH`, not `PYRENODE_BIN`/`PYRENODE_PKG`.** pyrenode3 0.0.1
   treats `PYRENODE_BIN`/`PYRENODE_PKG` as deprecated aliases and raises
   `ImportError: Multiple Renode paths are set` if more than one is exported. `env.sh` exports only
   `PYRENODE_PATH` (plus `PYRENODE_RUNTIME=coreclr` for compatibility; not read by pyrenode3 0.0.1).

## Open issues / risks carried into later phases

- **KiCad absent** (by design). Layout-dependent `ato` steps will warn/SKIP until
  `bash scripts/bootstrap.sh --with-kicad`.
- **No F411 Renode platform.** `plugin-renode` (Phase 4) should generate a `.repl` from
  `stm32f412.repl` with the exact F411 memory map / GPIO ports, rather than using a stock board.
- **QMK boot smoke is partial** (by brief design): runs without HardFault, but no UART banner
  asserted. Phase 4 adds a `keymaps/renode` debug-console build.
- **Machine-level, not repo:** standalone `~/.local/bin/uv` was added to survive the pyenv-shim +
  `.python-version` interaction; globals `turbo`/`biome` were installed into `~/.local/bin`. Future
  agents on this host get these for free; a fresh host needs `scripts/bootstrap.sh`.

## Root changes needed (orchestrator-owned files — not edited by this WP)

1. **PLAN.md §2 / §8**: replace `brew install --cask gcc-arm-embedded` with the formula path
   (`brew install arm-none-eabi-gcc` + `brew install osx-cross/arm/arm-gcc-bin@13`), and note
   `PYRENODE_PATH` (not `PYRENODE_BIN`) for pyrenode3.
2. **Root Python workspace (`pyproject.toml`, WP-1.0)**: set `requires-python = ">=3.14,<3.15"` to
   match `.python-version` and atopile 0.15.9.
3. **WP-1.4 CI**: this host's `env.sh` is macOS-specific; Linux CI should install the GNU Arm
   toolchain and Renode from the Docker image rather than reproducing these formulae. No repo file
   changes requested here — just do not assume `~/.atomc/env.sh` exists in CI.

## Notes for downstream WPs that depend on WP-0.1

- **WP-1.6 (`example-seed`)** can now `qmk compile` — `QMK_HOME=~/qmk_firmware` and the toolchain are
  ready. `qmk compile -kb handwired/onekey/blackpill_f411 -km default` is proven.
- Source `. ~/.atomc/env.sh` before invoking `renode`, `pyrenode3`, `qmk`, or `arm-none-eabi-gcc`.
