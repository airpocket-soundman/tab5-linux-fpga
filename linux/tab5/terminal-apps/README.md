# Tab5 terminal applications

This independent userspace build uses pinned Buildroot 2025.02.15 with an
RV32IMAC/ILP32 NOMMU uClibc-ng toolchain and static bFLT executables. It does
not rebuild the Linux kernel, ESP-IDF boot shim, or C6 firmware.

Run `.github/workflows/tab5-terminal-apps.yml`, or on Linux:

```sh
bash linux/tab5/terminal-apps/build.sh all
```

Local generated output defaults to `work/terminal-apps/` and `artifacts/`.
Keep those build outputs, SDK archives, and downloaded sources out of Git.

The CI saves the completed toolchain cache and a relocatable SDK before
building applications. After extracting the SDK, run `host/relocate-sdk.sh`
in its extracted location. Its architecture, libc, and headers are recorded
in `buildroot.config`; do not use a host Linux or ESP-IDF compiler instead.

The applications are genuine upstream Vim (tiny), nano (tiny), and sl.
Vim shell commands, external filters, and shell wildcard expansion are
disabled for NOMMU safety; they return an error. Job/channel/GUI/terminal
features and Vim's large runtime package are omitted. A minimal
`defaults.vim` is included so ordinary startup does not warn about a missing
runtime file. Multibyte support is
requested for Vim and wide-character ncurses is enabled. Actual Japanese
input/display still requires testing with the target terminal and locale.
Nano's tiny build omits shell-spawning features and several full-editor
features. These choices preserve ordinary interactive editing and saving
as the first runtime acceptance criterion; cross-compilation is not proof
of target operation.

The payload contains these three static applications, a small `fpga-link`
C mock test tool (no hardware backend), minimal Vim defaults, and terminfo, including
`vt102`, `linux`, `xterm`, and `xterm-256color`. It does not replace libc,
BusyBox, `vi`, firmware, kernel modules, or network daemons. Current board
network, SD, and display helpers are copied explicitly when repacking the
verified baseline rootfs. The LZ4 rootfs must fit its 7 MiB flash partition;
an oversized build fails and requires an explicit SD deployment choice.

The build records package licenses and recipes. Exact upstream versions
and source checksums are pinned by the selected Buildroot commit and its
package metadata. The source build and local Vim patch are reproducible
from this directory. See generated logs and `applications.json` for binary
hashes, sizes, and bFLT stack allocations.
