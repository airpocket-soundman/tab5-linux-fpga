################################################################################
# tab5-gpio: shared GPIO v2 core + shell client (Tab5 only)
################################################################################
TAB5_GPIO_VERSION = 1
TAB5_GPIO_SITE = $(BR2_EXTERNAL_EASYSTICK_STAMP_P4_PATH)/../tab5/gpio
TAB5_GPIO_SITE_METHOD = local
TAB5_GPIO_LICENSE = GPL-2.0-only
TAB5_GPIO_LICENSE_FILES = LICENSE

define TAB5_GPIO_BUILD_CMDS
	$(TARGET_CC) $(TARGET_CFLAGS) -std=c11 -Os -fPIC -static \
		-Wall -Wextra -Werror '-Wl,-elf2flt=-r -s32768' \
		$(@D)/tab5_gpio.c $(@D)/tab5_gpio_linux.c $(@D)/tab5_gpio_cli.c \
		-o $(@D)/tab5-gpio
endef

define TAB5_GPIO_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/tab5-gpio $(TARGET_DIR)/usr/bin/tab5-gpio
endef

$(eval $(generic-package))
