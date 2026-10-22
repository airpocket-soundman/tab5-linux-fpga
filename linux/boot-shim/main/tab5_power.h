/* SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only */
#pragma once

#include <stdbool.h>

/* Switch the Tab5's C6 supply on through the I2C IO expander. */
bool tab5_c6_power_on(void);

/* Release the panel reset and switch the backlight on. */
bool tab5_lcd_power_on(void);

/* Supply USB-A VBUS through expander 0x44 P3; preserve all other outputs. */
bool tab5_usb_host_power_on(void);
