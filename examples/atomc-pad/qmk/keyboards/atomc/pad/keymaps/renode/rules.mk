# Emulation/debug keymap only. QMK's print/debug sink is redirected to USART1
# in keymap.c; this pulls in the UART driver (uart_serial.c on ChibiOS/STM32).
CONSOLE_ENABLE = yes
DEBUG_MATRIX_SCAN_RATE_ENABLE = api
UART_DRIVER_REQUIRED = yes
