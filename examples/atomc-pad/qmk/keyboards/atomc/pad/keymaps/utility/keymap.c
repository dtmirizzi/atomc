// Copyright 2026 atomc contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Utility keymap for the atomc-pad 3x3 macropad.
// Layer 0 (BASE) is digits 1-9; hold the bottom-right key to reach the
// utility/media layer. The layer tap keeps KC_9 on a normal tap.
//
// This keymap is an alternative to the derived `default` keymap. The derived
// default remains a single-layer fixture for the plugin-qmk byte-for-byte
// goldens; this file supplies the base + media/utilities layer set requested
// by WP-4.4.

#include QMK_KEYBOARD_H

enum layer_names {
    _BASE,
    _UTIL,
};

const uint16_t PROGMEM keymaps[][MATRIX_ROWS][MATRIX_COLS] = {
    [_BASE] = LAYOUT(
        KC_1, KC_2, KC_3,
        KC_4, KC_5, KC_6,
        KC_7, KC_8, LT(_UTIL, KC_9)
    ),
    [_UTIL] = LAYOUT(
        KC_MUTE, KC_VOLD, KC_VOLU,
        KC_MPRV, KC_MPLY, KC_MNXT,
        KC_BRIU, KC_BRID, _______
    ),
};
