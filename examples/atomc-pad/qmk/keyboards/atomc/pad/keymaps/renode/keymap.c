// Copyright 2026 atomc contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Renode/emulation keymap for atomc-pad.
// Same key assignments as the default keymap plus matrix debug output on the
// console so Phase 4 emulation runs can correlate scans with captures.

#include QMK_KEYBOARD_H

const uint16_t PROGMEM keymaps[][MATRIX_ROWS][MATRIX_COLS] = {
    [0] = LAYOUT(
        KC_1, KC_2, KC_3,
        KC_4, KC_5, KC_6,
        KC_7, KC_8, KC_9
    ),
};

void keyboard_post_init_user(void) {
    debug_matrix = true;
    debug_keyboard = true;
}
