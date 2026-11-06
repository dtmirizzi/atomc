// Copyright 2026 atomc contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Renode/emulation keymap MCU overrides.
//
// The BLACKPILL_STM32_F411 board config leaves STM32_SERIAL_USE_USART1 FALSE.
// The renode keymap enables the QMK UART driver and routes debug output to
// USART1 on PA9/PA10, so this keymap-local mcuconf.h turns that peripheral on.
// Keep this file in the keymap directory so the default keymap stays untouched.

#pragma once

#include_next <mcuconf.h>

#undef STM32_SERIAL_USE_USART1
#define STM32_SERIAL_USE_USART1 TRUE
