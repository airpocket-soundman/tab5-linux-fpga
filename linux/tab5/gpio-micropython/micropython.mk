# SPDX-License-Identifier: GPL-2.0-only
# USER_C_MODULES must be linux/tab5, the parent of this module directory.
TAB5GPIO_MOD_DIR := $(USERMOD_DIR)
TAB5GPIO_CORE_DIR := $(TAB5GPIO_MOD_DIR)/../gpio
SRC_USERMOD_C += $(TAB5GPIO_MOD_DIR)/tab5gpio.c
SRC_USERMOD_LIB_C += $(TAB5GPIO_CORE_DIR)/tab5_gpio.c
CFLAGS_USERMOD += -I$(TAB5GPIO_CORE_DIR)

# Host test binaries only. Production has no runtime backend switch.
ifeq ($(TAB5_GPIO_TEST_BACKEND),1)
SRC_USERMOD_LIB_C += $(TAB5GPIO_MOD_DIR)/test_backend.c
CFLAGS_USERMOD += -DTAB5_GPIO_TEST_BACKEND=1
else
SRC_USERMOD_LIB_C += $(TAB5GPIO_CORE_DIR)/tab5_gpio_linux.c
endif
