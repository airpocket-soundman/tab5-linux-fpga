#!/bin/sh
# Install the same launcher under each supported /usr/bin application name.
# The SD mount is established and identified by S30tab5-sdcard.
name=${0##*/}
case "$name" in
 vim|nano|sl|fpga-link) ;;
 *) echo "terminal-apps: unsupported launcher name: $name" >&2; exit 127 ;;
esac

sd_root=/mnt/sdcard
mounts=/proc/mounts
mounted=
while read -r source target filesystem options rest; do
 [ "$target" = "$sd_root" ] || continue
 case "$filesystem" in vfat|exfat) ;; *) continue ;; esac
 case "$source" in
  /dev/mmcblk*p*)
   suffix=${source#/dev/mmcblk}
   disk=${suffix%%p*}
   partition=${suffix#*p}
   case "$disk" in ''|*[!0-9]*) continue ;; esac
   case "$partition" in ''|*[!0-9]*) continue ;; esac
   ;;
  *) continue ;;
 esac
 mounted=yes
 break
done < "$mounts"

if [ "$mounted" != yes ]; then
 echo "$name: microSD is not mounted at $sd_root as an SD FAT/exFAT partition; no RAM fallback" >&2
 exit 127
fi

application="$sd_root/tab5/apps/usr/bin/$name"
if [ ! -f "$application" ] || [ ! -x "$application" ]; then
 echo "$name: application is not installed or executable on microSD: $application" >&2
 exit 127
fi

TERMINFO="$sd_root/tab5/apps/usr/share/terminfo"
VIMRUNTIME="$sd_root/tab5/apps/usr/share/vim/vim91"
export TERMINFO VIMRUNTIME
exec "$application" "$@"
