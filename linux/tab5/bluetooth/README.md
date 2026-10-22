# Experimental Tab5 BLE keyboard host

This is an opt-in bring-up path, not a verified keyboard feature. The initial
target is the user's `K68 BT5.0`. C6 advertises capability `0x0d`: Wi-Fi SDIO,
Bluetooth SDIO and BLE-only. Classic-only keyboards are not supported.

## Build integration

Append `kernel.config.fragment` to the kernel configuration and run olddefconfig.
Build the ESP-Hosted host module from the exact pinned source, with all repository
patches, against that same kernel build. Pass `CONFIG_ESP_HOSTED_BLE=y` to the
module build. The Buildroot package translates `TAB5_BLE=1` to that option.
Without this explicit option patch 0007 still prevents HCI registration.
`CONFIG_BT` must be enabled for patch 0035 to include the HCI implementation.

The driver itself registers an SDIO HCI device; a separate generic Bluetooth
SDIO driver is not required. Keep the current C6 firmware initially. Kernel,
driver and Wi-Fi coexistence must be tested together before deployment.

Build the userspace program with the existing relocated static NOMMU SDK:

```sh
bash linux/tab5/bluetooth/build.sh /path/to/sdk /path/to/output
```

The program depends only on libc and Linux UAPI headers. It starts no subprocess,
thread, D-Bus daemon or BlueZ service. No third-party implementation is copied;
the program is distributed under GPL-2.0-only.

## Manual test

Do not autostart this experimental program. First verify Wi-Fi and `hci0` after
the new kernel and matching module have booted. Run as root on the serial console
so pairing does not depend on the untested Bluetooth input or Wi-Fi coexistence.

```sh
tab5-ble-hid --version
tab5-ble-hid scan K68
tab5-ble-hid connect AA:BB:CC:DD:EE:FF random
```

Use the address and `public` or `random` type printed by the scan. Put the
keyboard into BLE pairing mode. If a passkey is displayed, type it on the
keyboard and press Enter. A numeric-comparison request requires typing `yes` on
the host only after comparing both values. A host-passkey-entry request is
explicitly rejected by this initial DisplayOnly agent.
Just Works pairing is rejected: the ATT socket requires authenticated encryption
(`BT_SECURITY_HIGH`). A keyboard that supports only unauthenticated pairing
cannot be used with this initial host.

After the program reports `BLE HID input active`, key notifications are forwarded
through UHID into Linux input. Keep the process running; Ctrl-C closes the input
device and connection. Use another console to inspect `/proc/bus/input/devices`
and verify real key input on the VT. Successful compilation, scanning or pairing
alone does not establish successful keyboard input.

## Initial limits and outstanding verification

* One controller (`hci0`) and the first HID service with standard 16-bit UUIDs.
* Report-map/Report-Reference discovery, input reports and CCC notifications.
  UHID START must arrive before subscriptions are enabled; its numbered-input
  flag must agree with each Report Reference identifier.
* Linux handles SMP and link encryption; pair keys live only in the running
  kernel. Persistent bonds, reconnect and identity-resolution storage are not
  implemented. Pair again after a reboot.
* Output/feature reports and keyboard LED updates are not implemented. UHID
  requests needing these reports return an unsupported-operation error.
* Failed discovery, encryption or incompatible descriptors aborts the test.
* Kernel/module compilation, scan, passkey pairing, GATT discovery, input,
  disconnect and simultaneous Wi-Fi traffic all require actual-device tests.

Protocol references: [Linux management API](https://github.com/bluez/bluez/blob/5.79/doc/mgmt-api.txt),
[Linux UHID](https://docs.kernel.org/hid/uhid.html), and the Bluetooth ATT/GATT/HID
over GATT specifications. Avoid publishing pairing logs or private bond material.

## HCI buffer ownership audit (2026-10-23)

Patch `0037-easystick-bt-skb-ownership.patch` addresses the previously unbuilt
Bluetooth path. In Linux 6.18.35,
[`hci_send_frame()`](https://github.com/gregkh/linux/blob/v6.18.35/net/bluetooth/hci_core.c)
frees the original buffer if the driver's send callback returns a negative value.
`hci_recv_frame()` queues the receive buffer on success and frees it on error;
the driver must not inspect that buffer after either outcome.

The Bluetooth callback now creates a separate transport buffer without changing
the original. Allocation failure returns `-ENOMEM` with the original intact for
HCI core to free. A copy failure frees the copy and consumes the original as a
drop. Unsupported transport, absent adapter or missing write callback consumes
the original as a drop before allocating a copy. SDIO and SPI callbacks were
audited at pinned ESP-Hosted commit
`8626b42fd3f9eb5a1ccb5daea481f0d8d32b1685`:

* [SDIO write](https://github.com/espressif/esp-hosted/blob/8626b42fd3f9eb5a1ccb5daea481f0d8d32b1685/esp_hosted_ng/host/sdio/esp_sdio.c)
  frees its buffer for invalid context, oversize or backpressure errors; success
  transfers it to the transmission queue.
* [SPI write](https://github.com/espressif/esp-hosted/blob/8626b42fd3f9eb5a1ccb5daea481f0d8d32b1685/esp_hosted_ng/host/spi/esp_spi.c)
  likewise consumes it, including the closed-data-path error.
* The generic `esp_send_packet()` missing-adapter/ops error does not free its
  argument. Bluetooth therefore calls the validated SDIO/SPI callback directly.
  The existing driver lifecycle must keep adapter/ops valid during HCI sends.

After transport submission the original is consumed and the callback returns
zero, including transport drops. Drops increment `err_tx`; a zero callback return
means buffer ownership was accepted, not that the controller received the frame.
Successful submissions update counters using saved type/length only. Receive
statistics likewise use metadata saved before `hci_recv_frame()`. Registration
failure clears `adapter->hcidev` after freeing its HCI device. Wi-Fi paths are
unchanged. Patch application is checked; kernel/module compilation and device
behavior remain separate verification steps.
