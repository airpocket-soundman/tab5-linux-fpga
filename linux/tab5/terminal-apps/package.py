#!/usr/bin/env python3
"""Prepare static apps and merge them into a verified baseline rootfs."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import tarfile
from zipfile import ZipFile

HELPERS = (
    'etc/init.d/S03loopback', 'usr/sbin/tab5-wifi', 'etc/profile',
    'etc/init.d/S30tab5-sdcard', 'etc/init.d/S99tab5-display',
    'etc/init.d/S98tab5-touch-scroll',
)


def hashes(text):
    result = {}
    for line in text.splitlines():
        digest, name = line.split(maxsplit=1)
        result[name.lstrip('*')] = digest
    return result


def check(data, digest, name):
    if hashlib.sha256(data).hexdigest() != digest:
        raise SystemExit(f'SHA-256 mismatch: {name}')


def payload(output, artifacts):
    target = output / 'target'
    dest = artifacts / 'payload'
    if dest.exists():
        shutil.rmtree(dest)
    (dest / 'usr/bin').mkdir(parents=True)
    manifest = {}
    for app in ('vim', 'nano', 'sl', 'fpga-link', 'tab5-touch-scroll', 'tab5-ble-hid'):
        source = target / 'usr/bin' / app
        if source.is_symlink() or not source.is_file():
            raise SystemExit(f'Expected genuine application binary: {source}')
        data = bytearray(source.read_bytes())
        if len(data) < 64 or data[:4] != b'bFLT':
            raise SystemExit(f'Expected static NOMMU bFLT executable: {app}')
        header = struct.unpack('>4s15I', data[:64])
        if header[1] != 4 or header[9] & 0x0c:
            raise SystemExit(f'Unexpected bFLT revision/compression: {app}')
        stack = 262144 if app == 'vim' else (65536 if app in ('nano', 'tab5-ble-hid') else 32768)
        struct.pack_into('>I', data, 24, stack)
        binary = dest / 'usr/bin' / app
        binary.write_bytes(data)
        binary.chmod(0o755)
        manifest[app] = {
            'bytes': len(data), 'stack_bytes': stack,
            'bss_end': header[5],
            'sha256': hashlib.sha256(data).hexdigest(),
        }
    terminfo = target / 'usr/share/terminfo'
    for terminal in ('v/vt102', 'l/linux', 'x/xterm', 'x/xterm-256color'):
        if not (terminfo / terminal).is_file():
            raise SystemExit(f'Missing required terminfo: {terminal}')
    shutil.copytree(terminfo, dest / 'usr/share/terminfo')
    # Buildroot omits the large runtime package. Vim still sources defaults.vim
    # on ordinary startup, so ship a small explicit default for pinned Vim 9.1.
    runtime = dest / 'usr/share/vim/vim91'
    runtime.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(__file__).with_name('defaults.vim'), runtime / 'defaults.vim')
    (artifacts / 'applications.json').write_text(json.dumps(manifest, indent=2) + '\n')
    with tarfile.open(artifacts / 'tab5-terminal-apps.tar.gz', 'w:gz') as archive:
        archive.add(dest / 'usr', arcname='usr')
    print(json.dumps(manifest, indent=2))


def baseline(folder):
    name = 'm5stamp-p4-c6-linux-smp-v0.0.1.zip'
    expected = hashes((folder / 'SHA256SUMS.txt').read_text())
    data = (folder / name).read_bytes()
    check(data, expected[name], name)
    with ZipFile(folder / name) as archive:
        expected = hashes(archive.read('SHA256SUMS.txt').decode())
        image = archive.read('rootfs.squashfs')
        check(image, expected['rootfs.squashfs'], 'rootfs.squashfs')
        (folder / 'rootfs.squashfs').write_bytes(image)


def install(rootfs, artifacts, overlay, storage="internal"):
    if storage == 'internal':
        # Requires kernel patch 0080: exact 7 MiB ROM mapping.
        shutil.copytree(artifacts / 'payload/usr', rootfs / 'usr', dirs_exist_ok=True)
    elif storage == 'sd':
        launcher = Path(__file__).with_name('launcher.sh')
        for app in ('vim', 'nano', 'sl', 'fpga-link'):
            target = rootfs / 'usr/bin' / app
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink():
                target.unlink()
            shutil.copyfile(launcher, target)
            target.chmod(0o755)
        # Console input must work even when the SD application tree is absent.
        for helper in ('tab5-touch-scroll', 'tab5-ble-hid'):
            target = rootfs / 'usr/bin' / helper
            shutil.copyfile(artifacts / 'payload/usr/bin' / helper, target)
            target.chmod(0o755)
    else:
        raise SystemExit('storage must be internal or sd')
    for name in HELPERS:
        source = overlay / name
        target = rootfs / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            target.unlink()
        shutil.copyfile(source, target)
        target.chmod(0o644 if name == 'etc/profile' else 0o755)
    (rootfs / 'mnt/sdcard').mkdir(parents=True, exist_ok=True)


if __name__ == '__main__':
    mode, *args = sys.argv[1:]
    if mode == 'baseline' and len(args) == 1:
        baseline(Path(args[0]))
    elif mode == 'install' and len(args) in (3, 4):
        install(*(Path(arg) for arg in args[:3]), storage=args[3] if len(args) == 4 else 'internal')
    elif len(sys.argv) == 3:
        payload(Path(sys.argv[1]), Path(sys.argv[2]))
    else:
        raise SystemExit('Usage: package.py OUTPUT ARTIFACTS | baseline FOLDER | install ROOTFS ARTIFACTS OVERLAY')
