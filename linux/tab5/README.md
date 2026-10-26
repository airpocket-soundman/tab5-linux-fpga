# Tab5 peripheral integration

This directory owns Tab5 kernel fragments. Board wiring lives in
`../dts/tab5-overrides.dtsi`, early power/clock setup in `../boot-shim/`.
The one-core baseline remains unchanged.

`tab5-gpio`, `tab5-peripherals`, `tab5-image` and `tab5-camera` are installed
on Tab5 builds. The MicroPython package adds `tab5io.Pin` when these tools
are selected. GPIO uses
Linux's v2 character-device API, not raw MMIO or global sysfs numbering.
It still needs the board GPIO driver, correct chip/offset selection, and
hardware verification. The tool does not know board reservations: a line
not requested by a Linux driver can still belong to onboard hardware.

The USB classes fragment is opt-in via `EASYSTICK_TAB5_USB_CLASSES=1`.
It adds storage/SCSI/FAT/exFAT, UVC/V4L2, USB HID and Ethernet classes for subsequent host work;
it does not enable a controller, assign pins, or power VBUS. Check the final
kernel `.config` because Kconfig may drop unsupported dependencies. Do not
infer USB operation from fragment contents or successful compilation.

The existing FS OTG node must stay disabled on Tab5: GPIO26/27 are used for
audio. Tab5's external USB host needs the separate HS controller/PHY path.
MeOS's direct-register DMA implementation cannot run as a Linux driver.

See [feature status and acceptance steps](../../docs/TAB5_PERIPHERALS.md).
The broader [MeOS feature audit](../../docs/MEOS_FEATURE_PARITY.md) tracks remaining drivers.
