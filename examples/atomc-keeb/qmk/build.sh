#!/usr/bin/env bash
# Build the atomc-keeb QMK firmware (default + renode keymaps).
#
# Symlinks this repository's `keyboards/atomc` tree into $QMK_HOME/keyboards/atomc
# and invokes `qmk compile`. Requires QMK_HOME to point at a qmk_firmware checkout
# (default: ~/qmk_firmware) and the QMK CLI on PATH.
#
# Usage: ./build.sh [default|renode|all]   (default: all)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QMK_HOME="${QMK_HOME:-$HOME/qmk_firmware}"
KEYMAP="${1:-all}"

if [ ! -d "$QMK_HOME" ]; then
    echo "error: QMK_HOME=$QMK_HOME does not exist" >&2
    echo "       run: qmk setup -H \"$QMK_HOME\"" >&2
    exit 1
fi

# Link the atomc keyboards into the QMK tree. Replace any stale symlink.
mkdir -p "$QMK_HOME/keyboards/atomc"
for kb in "$HERE"/keyboards/atomc/*/; do
    name="$(basename "$kb")"
    rm -rf "$QMK_HOME/keyboards/atomc/$name"
    ln -sfn "$kb" "$QMK_HOME/keyboards/atomc/$name"
done

build_keymap() {
    local km="$1"
    echo "==> qmk compile -kb atomc/keeb -km $km"
    qmk compile -kb atomc/keeb -km "$km"
}

case "$KEYMAP" in
    default) build_keymap default ;;
    renode)  build_keymap renode ;;
    all)     build_keymap default; build_keymap renode ;;
    *) echo "error: unknown keymap '$KEYMAP'" >&2; exit 2 ;;
esac
