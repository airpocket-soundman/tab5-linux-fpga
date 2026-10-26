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
ifeq ($(BR2_PACKAGE_TAB5_TOOLS),y)
MICROPYTHON_NOMMU_LICENSE_FILES += tab5io-LICENSE
MICROPYTHON_NOMMU_USER_MODULES = USER_C_MODULES=$(MICROPYTHON_NOMMU_PKGDIR)/usermod
define MICROPYTHON_NOMMU_INSTALL_TAB5_LICENSE
	cp $(MICROPYTHON_NOMMU_PKGDIR)/usermod/tab5io/LICENSE $(@D)/tab5io-LICENSE
endef
MICROPYTHON_NOMMU_POST_PATCH_HOOKS += MICROPYTHON_NOMMU_INSTALL_TAB5_LICENSE
endif
MICROPYTHON_NOMMU_DEPENDENCIES = host-python3

# variant/: the unix "standard" modules within the NOMMU size budget (#34).
define MICROPYTHON_NOMMU_INSTALL_VARIANT
	mkdir -p $(@D)/ports/unix/variants/nommu
	cp $(MICROPYTHON_NOMMU_PKGDIR)/variant/* $(@D)/ports/unix/variants/nommu/
endef
MICROPYTHON_NOMMU_POST_PATCH_HOOKS += MICROPYTHON_NOMMU_INSTALL_VARIANT

define MICROPYTHON_NOMMU_BUILD_CMDS
	$(TARGET_MAKE_ENV) $(MAKE) -C $(@D)/mpy-cross
	$(TARGET_MAKE_ENV) $(MAKE) -C $(@D)/ports/unix \
		VARIANT=nommu \
		$(MICROPYTHON_NOMMU_USER_MODULES) \
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
