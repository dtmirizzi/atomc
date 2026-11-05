#!/usr/bin/env bash
# atomc Phase 0 environment bootstrap (WP-0.1)
#
# Idempotent installer for every external toolchain the atomc monorepo needs on
# macOS arm64. Safe to run repeatedly: each step detects an already-satisfied
# precondition and skips.
#
# Usage:
#   bash scripts/bootstrap.sh              # install everything except KiCad
#   bash scripts/bootstrap.sh --with-kicad # also install the KiCad GUI cask
#
# Notes:
#   * Never uses sudo.
#   * Writes shared env exports to ~/.atomc/env.sh (does NOT touch shell rc files).
#   * See docs/plan/ENVIRONMENT.md for versions and workarounds.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_DIR="${HOME}/.atomc"
ENV_FILE="${ENV_DIR}/env.sh"
OPT_DIR="${HOME}/.local/opt"
BIN_DIR="${HOME}/.local/bin"
RENODE_VERSION="1.17.0"
RENODE_DIR="${OPT_DIR}/renode-${RENODE_VERSION}"
RENODE_DMG_URL="https://github.com/renode/renode/releases/download/v${RENODE_VERSION}/renode-${RENODE_VERSION}.osx-arm64-portable.dmg"
PYTHON_PIN="3.14"
ATOPILE_VERSION="0.15.9"
VENV="${REPO_ROOT}/.venv"

WITH_KICAD=0
for arg in "$@"; do
  case "$arg" in
    --with-kicad) WITH_KICAD=1 ;;
    -h|--help) sed -n '1,20p' "$0"; exit 0 ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

STEP=0
step()  { STEP=$((STEP + 1)); printf '\n\033[1;34m==> [%02d] %s\033[0m\n' "$STEP" "$*"; }
info()  { printf '    %s\n' "$*"; }
skip()  { printf '    \033[32mskip\033[0m %s\n' "$*"; }
warn()  { printf '    \033[33mwarn\033[0m %s\n' "$*"; }
die()   { printf '    \033[31mfail\033[0m %s\n' "$*" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

mkdir -p "$ENV_DIR" "$OPT_DIR" "$BIN_DIR"

# ---------------------------------------------------------------------------
step "Preconditions (macOS arm64, Homebrew, uv)"
[[ "$(uname -s)" == "Darwin" ]] || die "this bootstrap targets macOS"
[[ "$(uname -m)" == "arm64" ]] || die "this bootstrap targets arm64 (got $(uname -m))"
have brew || die "Homebrew not found"
have uv   || die "uv not found (https://docs.astral.sh/uv/)"
info "macOS $(sw_vers -productVersion) $(uname -m), brew $(brew --version | head -1 | awk '{print $2}')"

# Resolve a real uv binary. On machines where uv was installed into a pyenv
# version, `~/.pyenv/shims/uv` is only a shim: once this repo's .python-version
# (3.14) is honored by pyenv, the shim looks for uv inside 3.14 and fails. We
# therefore prefer the standalone binary and copy it to ~/.local/bin (which
# precedes ~/.pyenv/shims on PATH) so uv keeps working after the pin is written.
resolve_uv() {
  local cand
  for cand in "${HOME}/.local/bin/uv" /opt/homebrew/bin/uv "${HOME}/.cargo/bin/uv"; do
    [[ -x "${cand}" ]] && { printf '%s\n' "${cand}"; return; }
  done
  for cand in $(ls -1 "${HOME}"/.pyenv/versions/*/bin/uv 2>/dev/null | sort -Vr); do
    [[ -x "${cand}" ]] && { printf '%s\n' "${cand}"; return; }
  done
  command -v uv
}
UV="$(resolve_uv)"
[[ -n "${UV}" ]] || die "could not resolve a uv binary"
info "uv $(${UV} --version | awk '{print $2}') at ${UV}"

# ---------------------------------------------------------------------------
step "Standalone uv on PATH (~/.local/bin precedes pyenv shims)"
if [[ -x "${BIN_DIR}/uv" ]]; then
  skip "${BIN_DIR}/uv"
else
  mkdir -p "${BIN_DIR}"
  cp "${UV}" "${BIN_DIR}/uv"
  chmod +x "${BIN_DIR}/uv"
  UV="${BIN_DIR}/uv"
  info "installed standalone uv -> ${BIN_DIR}/uv"
fi

# ---------------------------------------------------------------------------
step "Python ${PYTHON_PIN} via uv + .python-version"
if ${UV} python list --only-installed 2>/dev/null | grep -qE "cpython-${PYTHON_PIN}\."; then
  skip "python ${PYTHON_PIN} already installed"
else
  ${UV} python install "${PYTHON_PIN}"
fi
if [[ "$(cat "${REPO_ROOT}/.python-version" 2>/dev/null || true)" == "${PYTHON_PIN}" ]]; then
  skip ".python-version already pinned to ${PYTHON_PIN}"
else
  printf '%s\n' "${PYTHON_PIN}" > "${REPO_ROOT}/.python-version"
  info "wrote .python-version = ${PYTHON_PIN}"
fi

# ---------------------------------------------------------------------------
step "atopile ${ATOPILE_VERSION} via uv tool"
if have ato && ato --version 2>/dev/null | grep -q "${ATOPILE_VERSION}"; then
  skip "ato ${ATOPILE_VERSION} already installed"
else
  ${UV} tool install "atopile==${ATOPILE_VERSION}"
fi

# ---------------------------------------------------------------------------
step "Homebrew: dotnet@8, cmake, ninja"
BREW_FORMULAE=(dotnet@8 cmake ninja)
for f in "${BREW_FORMULAE[@]}"; do
  if brew list --formula "$f" >/dev/null 2>&1; then
    skip "formula $f"
  else
    brew install "$f"
  fi
done

# ---------------------------------------------------------------------------
step "arm-none-eabi-gcc (user-space toolchains; no sudo/cask)"
# Two toolchains are needed and neither may use sudo:
#  * homebrew/core `arm-none-eabi-gcc` - bare compiler (no newlib specs).
#  * osx-cross/arm `arm-gcc-bin@13` (keg-only) - full GNU Arm toolchain with
#    the `nosys.specs`/`nano.specs` that QMK's compiler probe requires.
# The `gcc-arm-embedded` cask runs a .pkg via sudo and is intentionally unused.
if brew info --formula arm-none-eabi-gcc >/dev/null 2>&1; then
  if brew list --formula arm-none-eabi-gcc >/dev/null 2>&1; then
    skip "homebrew/core arm-none-eabi-gcc"
  else
    brew install arm-none-eabi-gcc
  fi
fi
if brew list osx-cross/arm/arm-gcc-bin@13 >/dev/null 2>&1; then
  skip "osx-cross/arm/arm-gcc-bin@13"
else
  brew tap osx-cross/arm || true
  brew trust osx-cross/arm >/dev/null 2>&1 || true
  brew install osx-cross/arm/arm-gcc-bin@13 || die "could not install a full arm-none-eabi toolchain without sudo"
fi
ARM_GCC_PREFIX="$(brew --prefix osx-cross/arm/arm-gcc-bin@13 2>/dev/null || true)"

# ---------------------------------------------------------------------------
step "QMK AVR/aux dependencies (formulae only, no sudo)"
# Not needed for the STM32F411 target, but `qmk doctor` requires them; QMK's
# macOS guidance uses the osx-cross tap for avr-gcc.
QMK_DEPS=(avrdude dfu-programmer dfu-util dos2unix)
for f in "${QMK_DEPS[@]}"; do
  if brew list --formula "$f" >/dev/null 2>&1; then
    skip "formula $f"
  else
    brew install "$f"
  fi
done
if brew list osx-cross/avr/avr-gcc@9 >/dev/null 2>&1; then
  skip "osx-cross/avr/avr-gcc@9"
else
  brew tap osx-cross/avr || true
  brew trust osx-cross/avr >/dev/null 2>&1 || true
  brew install osx-cross/avr/avr-gcc@9
fi

# ---------------------------------------------------------------------------
step "Renode ${RENODE_VERSION} (osx-arm64 portable)"
if [[ -x "${RENODE_DIR}/Renode.app/Contents/MacOS/Renode" ]] && [[ -L "${BIN_DIR}/renode" ]]; then
  skip "Renode ${RENODE_VERSION} already installed at ${RENODE_DIR}"
else
  tmp_dmg="$(mktemp -t renode-${RENODE_VERSION}.XXXXXX).dmg"
  info "downloading ${RENODE_DMG_URL}"
  curl -fL --retry 3 -o "${tmp_dmg}" "${RENODE_DMG_URL}" || die "Renode download failed"
  mnt="$(mktemp -d -t renode-mnt.XXXXXX)"
  info "mounting dmg"
  hdiutil attach "${tmp_dmg}" -nobrowse -quiet -mountpoint "${mnt}" || die "could not mount Renode dmg"
  app="$(find "${mnt}" -maxdepth 1 -name '*.app' -print -quit)"
  [[ -n "${app}" ]] || { hdiutil detach "${mnt}" -quiet || true; die "no .app found in dmg"; }
  rm -rf "${RENODE_DIR}"
  mkdir -p "${RENODE_DIR}"
  info "copying $(basename "${app}") -> ${RENODE_DIR}/"
  cp -R "${app}" "${RENODE_DIR}/"
  hdiutil detach "${mnt}" -quiet || true
  rm -rf "${mnt}" "${tmp_dmg}"
  # Renode.app is unsigned/quarantined; clear it so Gatekeeper does not block it.
  xattr -dr com.apple.quarantine "${RENODE_DIR}/Renode.app" 2>/dev/null || true
  ln -sfn "${RENODE_DIR}/Renode.app/Contents/MacOS/Renode" "${BIN_DIR}/renode"
  info "symlinked ${BIN_DIR}/renode"
fi

# ---------------------------------------------------------------------------
step "Node/pnpm toolchain + global turbo & biome"
if have node; then
  node_major="$(node --version | sed 's/^v//' | cut -d. -f1)"
  [[ "${node_major}" -ge 22 ]] || die "node >= 22 required (found $(node --version))"
  info "node $(node --version)"
else
  die "node not found"
fi
if have pnpm; then
  info "pnpm $(pnpm --version)"
else
  die "pnpm not found"
fi
GLOBAL_NEEDS=()
have turbo || GLOBAL_NEEDS+=(turbo@latest)
have biome || GLOBAL_NEEDS+=(@biomejs/biome@latest)
if [[ ${#GLOBAL_NEEDS[@]} -gt 0 ]]; then
  # pnpm has no global bin dir configured on this machine and `pnpm setup`
  # edits shell rc files (forbidden here). Point PNPM_HOME at ~/.local/bin,
  # which is already on PATH, just for this install.
  PNPM_HOME="${BIN_DIR}" pnpm add -g "${GLOBAL_NEEDS[@]}"
else
  skip "turbo + biome already installed globally"
fi

# ---------------------------------------------------------------------------
step "Verification venv (build123d / OCP / kiutils / trimesh / pyrenode3)"
if [[ -x "${VENV}/bin/python" ]] && "${VENV}/bin/python" -c \
     'import importlib.util as u; assert all(u.find_spec(m) for m in ("build123d","OCP","kiutils","trimesh","pyrenode3"))' >/dev/null 2>&1; then
  skip "verification venv already populated"
else
  if [[ ! -x "${VENV}/bin/python" ]]; then
    ${UV} venv --python "${PYTHON_PIN}" "${VENV}"
  fi
  ${UV} pip install --python "${VENV}/bin/python" \
    "build123d==0.13.0" \
    "cadquery-ocp" \
    kiutils \
    trimesh \
    pydantic \
    "pyrenode3 @ git+https://github.com/antmicro/pyrenode3"
fi

# ---------------------------------------------------------------------------
step "QMK CLI + qmk_firmware"
if have qmk; then
  skip "qmk CLI already installed ($(qmk --version 2>/dev/null || echo unknown))"
else
  ${UV} tool install qmk
fi
if [[ -d "${HOME}/qmk_firmware/.git" ]]; then
  skip "qmk_firmware already cloned at ~/qmk_firmware"
else
  info "running qmk setup (clones qmk_firmware + submodules; this is large)"
  # Put the full GNU Arm toolchain first so QMK's compiler probe passes; -y
  # auto-accepts prompts without touching shell rc files or using sudo.
  PATH="${ARM_GCC_PREFIX}/bin:${PATH}" QMK_HOME="${HOME}/qmk_firmware" \
    qmk setup -y -H "${HOME}/qmk_firmware"
fi

# ---------------------------------------------------------------------------
step "Shared environment exports (~/.atomc/env.sh)"
DOTNET_PREFIX="$(brew --prefix dotnet@8 2>/dev/null || true)"
RENODE_MACOS="${RENODE_DIR}/Renode.app/Contents/MacOS"
{
  echo "# generated by atomc scripts/bootstrap.sh - source me: . ~/.atomc/env.sh"
  echo "# pyrenode3 reads PYRENODE_PATH (aliases PYRENODE_PKG/BIN are deprecated and must NOT be set together)"
  echo "export PYRENODE_PATH=\"${RENODE_DIR}/Renode.app/Contents/MacOS/Renode\""
  echo "export PYRENODE_RUNTIME=\"coreclr\""
  echo "export QMK_HOME=\"\${HOME}/qmk_firmware\""
  echo "export PATH=\"${BIN_DIR}:${RENODE_MACOS}:\$PATH\""
  if [[ -n "${ARM_GCC_PREFIX}" ]]; then
    # Keg-only full GNU Arm toolchain must precede homebrew/core's bare gcc.
    echo "export PATH=\"${ARM_GCC_PREFIX}/bin:\$PATH\""
  fi
  if [[ -n "${DOTNET_PREFIX}" ]]; then
    echo "export DOTNET_ROOT=\"${DOTNET_PREFIX}/libexec\""
    echo "export PATH=\"${DOTNET_PREFIX}/bin:\$PATH\""
  fi
} > "${ENV_FILE}"
info "wrote ${ENV_FILE}"

if [[ "${WITH_KICAD}" -eq 1 ]]; then
  step "KiCad cask (optional)"
  if brew list --cask kicad >/dev/null 2>&1; then
    skip "kicad"
  else
    brew install --cask kicad
  fi
else
  info "KiCad not requested (pass --with-kicad to install)"
fi

printf '\n\033[1;32mBootstrap complete.\033[0m\n'
printf 'Source the environment before using Renode/pyrenode3/QMK:\n\n'
printf '    . %s\n\n' "${ENV_FILE}"
printf 'Then verify with:  python3 scripts/doctor.py\n'
