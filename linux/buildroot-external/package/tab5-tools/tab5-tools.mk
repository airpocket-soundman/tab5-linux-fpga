TAB5_TOOLS_VERSION = 1
TAB5_TOOLS_SITE = $(BR2_EXTERNAL_EASYSTICK_STAMP_P4_PATH)/package/tab5-tools/src
TAB5_TOOLS_SITE_METHOD = local
TAB5_TOOLS_LICENSE = MIT
TAB5_TOOLS_LICENSE_FILES = LICENSE
# The row codec/viewer uses about 20 KiB of nested stack, including libc.
ifeq ($(BR2_BINFMT_FLAT),y)
TAB5_TOOLS_STACK_LDFLAGS = -Wl,-elf2flt=-s32768
endif

define TAB5_TOOLS_BUILD_CMDS
	$(TARGET_CC) $(TARGET_CFLAGS) -Wall -Wextra -Werror $(@D)/tab5-gpio.c \
		-o $(@D)/tab5-gpio $(TARGET_LDFLAGS) $(TAB5_TOOLS_STACK_LDFLAGS)
	$(TARGET_CC) $(TARGET_CFLAGS) -Wall -Wextra -Werror $(@D)/tab5-image.c $(@D)/bmp.c \
		-o $(@D)/tab5-image $(TARGET_LDFLAGS) $(TAB5_TOOLS_STACK_LDFLAGS)
	$(TARGET_CC) $(TARGET_CFLAGS) -Wall -Wextra -Werror $(@D)/tab5-camera.c $(@D)/bmp.c \
		-o $(@D)/tab5-camera $(TARGET_LDFLAGS) $(TAB5_TOOLS_STACK_LDFLAGS)
endef

define TAB5_TOOLS_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/tab5-gpio $(TARGET_DIR)/usr/bin/tab5-gpio
	$(INSTALL) -D -m 0755 $(@D)/tab5-peripherals $(TARGET_DIR)/usr/bin/tab5-peripherals
	$(INSTALL) -D -m 0755 $(@D)/tab5-image $(TARGET_DIR)/usr/bin/tab5-image
	$(INSTALL) -D -m 0755 $(@D)/tab5-camera $(TARGET_DIR)/usr/bin/tab5-camera
endef

$(eval $(generic-package))
