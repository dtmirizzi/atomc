// Copyright 2026 atomc contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Default keymap for the atomc-pad 3x3 macropad.
// Layout is a single BASE layer mapping the 3x3 matrix to digits 1-9.

#include QMK_KEYBOARD_H

const uint16_t PROGMEM keymaps[][MATRIX_ROWS][MATRIX_COLS] = {
    [0] = LAYOUT(
        KC_1, KC_2, KC_3,
        KC_4, KC_5, KC_6,
        KC_7, KC_8, KC_9
    ),
};
