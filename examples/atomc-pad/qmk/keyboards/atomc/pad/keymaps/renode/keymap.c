// Copyright 2026 atomc contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Renode/emulation keymap for atomc-pad.
//
// EMULATION BUILD ONLY. This keymap routes QMK's debug/console output to the
// USART1 TX/RX pads (A9/A10) so a Renode run can correlate matrix scans with a
// capture. It does NOT claim USB HID works under emulation, and it is not the
// keymap to flash when validating USB enumeration on hardware.
//
// The key assignments match the derived default keymap (digits 1-9). The
// additional `utility` keymap supplies the layer set.

#include QMK_KEYBOARD_H
#include "uart.h"
#include "print.h"

const uint16_t PROGMEM keymaps[][MATRIX_ROWS][MATRIX_COLS] = {
    [0] = LAYOUT(
        KC_1, KC_2, KC_3,
        KC_4, KC_5, KC_6,
        KC_7, KC_8, KC_9
    ),
};

// Redirect QMK's print/debug sink to USART1. Called by the core after
// keyboard_setup(); the UART driver must be enabled in rules.mk with
// UART_DRIVER_REQUIRED = yes.
static int8_t uart_sendchar(uint8_t c) {
    uart_write(c);
    return 0;
}

void keyboard_post_init_user(void) {
    uart_init(115200);
    print_set_sendchar(uart_sendchar);

    debug_enable   = true;
    debug_matrix   = true;
    debug_keyboard = true;
}
