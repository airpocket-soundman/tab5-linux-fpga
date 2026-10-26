################################################################################
#
# micropython-nommu
#
################################################################################

MICROPYTHON_NOMMU_VERSION = 1.22.2
MICROPYTHON_NOMMU_SITE = https://micropython.org/resources/source
MICROPYTHON_NOMMU_SOURCE = micropython-$(MICROPYTHON_NOMMU_VERSION).tar.xz
MICROPYTHON_NOMMU_LICENSE = MIT
MICROPYTHON_NOMMU_LICENSE_FILES = LICENSE
MICROPYTHON_NOMMU_DEPENDENCIES = host-python3

# Share the exact same policy and line lifetime code with the shell client.
ifeq ($(BR2_PACKAGE_TAB5_GPIO),y)
MICROPYTHON_NOMMU_DEPENDENCIES += tab5-gpio
MICROPYTHON_NOMMU_LICENSE = MIT, GPL-2.0-only
MICROPYTHON_NOMMU_LICENSE_FILES += COPYING.GPIO
MICROPYTHON_NOMMU_GPIO_SOURCE = $(BR2_EXTERNAL_EASYSTICK_STAMP_P4_PATH)/../tab5
MICROPYTHON_NOMMU_USERMOD_ARGS = USER_C_MODULES="$(@D)/usermods" TAB5_GPIO_TEST_BACKEND=0
define MICROPYTHON_NOMMU_INSTALL_GPIO
	cp $(MICROPYTHON_NOMMU_GPIO_SOURCE)/gpio/LICENSE $(@D)/COPYING.GPIO
	mkdir -p $(@D)/usermods/gpio $(@D)/usermods/gpio-micropython
	cp $(MICROPYTHON_NOMMU_GPIO_SOURCE)/gpio/tab5_gpio.h \
		$(MICROPYTHON_NOMMU_GPIO_SOURCE)/gpio/tab5_gpio.c \
		$(MICROPYTHON_NOMMU_GPIO_SOURCE)/gpio/tab5_gpio_linux.c $(@D)/usermods/gpio/
	cp $(MICROPYTHON_NOMMU_GPIO_SOURCE)/gpio-micropython/tab5gpio.c \
		$(MICROPYTHON_NOMMU_GPIO_SOURCE)/gpio-micropython/micropython.mk \
		$(@D)/usermods/gpio-micropython/
endef
MICROPYTHON_NOMMU_POST_PATCH_HOOKS += MICROPYTHON_NOMMU_INSTALL_GPIO
endif

# variant/: the unix "standard" modules within the NOMMU size budget (#34).
define MICROPYTHON_NOMMU_INSTALL_VARIANT
	mkdir -p $(@D)/ports/unix/variants/nommu
	cp $(MICROPYTHON_NOMMU_PKGDIR)/variant/* $(@D)/ports/unix/variants/nommu/
endef
MICROPYTHON_NOMMU_POST_PATCH_HOOKS += MICROPYTHON_NOMMU_INSTALL_VARIANT

define MICROPYTHON_NOMMU_BUILD_CMDS
	$(TARGET_MAKE_ENV) $(MAKE) -C $(@D)/mpy-cross
	$(TARGET_MAKE_ENV) $(MAKE) -C $(@D)/ports/unix \
		VARIANT=nommu $(MICROPYTHON_NOMMU_USERMOD_ARGS) \
		CROSS_COMPILE="$(TARGET_CROSS)" \
		CFLAGS_EXTRA="-fPIC -DMICROPY_GCREGS_SETJMP=1 -DMICROPY_NLR_SETJMP=1 -Wno-error" \
		LDFLAGS_EXTRA="-fPIC -Wl,-elf2flt=-r -Wl,-elf2flt=-s32768 -Wl,--allow-multiple-definition" \
		STRIP=true \
		SIZE=true
endef

define MICROPYTHON_NOMMU_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/ports/unix/build-nommu/micropython \
		$(TARGET_DIR)/usr/bin/micropython
	ln -sf micropython $(TARGET_DIR)/usr/bin/python3
	ln -sf micropython $(TARGET_DIR)/usr/bin/python
endef

$(eval $(generic-package))
