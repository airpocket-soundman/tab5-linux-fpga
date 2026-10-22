#!/usr/bin/env bash
# Package and exercise a relocated SDK without requiring Buildroot's world.
set -euo pipefail
[[ $# -eq 3 ]] || { echo "Usage: $0 BUILDROOT_SOURCE OUTPUT SDK_ARTIFACTS" >&2; exit 2; }
source_dir=$(cd -- "$1" && pwd)
output=$(cd -- "$2" && pwd)
mkdir -p -- "$3"
artifacts=$(cd -- "$3" && pwd)
host="$output/host"
compiler="$host/bin/riscv32-buildroot-linux-uclibc-gcc"
test -x "$compiler"
export LC_ALL=C

# `make toolchain` skips world -> host-finalize, so do the required host
# RPATH finalization explicitly before creating relocation text metadata.
# Use Buildroot's patched patchelf: the system utility lacks this interface.
make_args=(-C "$source_dir" O="$output")
if [[ -d "${output%/*}/downloads" ]]; then
    make_args+=(BR2_DL_DIR="${output%/*}/downloads")
fi
make "${make_args[@]}" -j"${TAB5_APPS_JOBS:-4}" host-patchelf
staging=$("$compiler" -print-sysroot)
staging=$(cd -- "$staging" && pwd)
[[ "$staging" == "$host/"* ]] || { echo 'Sysroot is outside this host SDK' >&2; exit 1; }
export HOST_DIR="$host" STAGING_DIR="$staging" TARGET_DIR="$output/target"
export PER_PACKAGE_DIR="$output/per-package" PARALLEL_JOBS="${TAB5_APPS_JOBS:-4}"
export PATCHELF="$host/bin/patchelf"
bash "$source_dir/support/scripts/fix-rpath" host
bash "$source_dir/support/scripts/fix-rpath" staging

# Official relocate-sdk.sh rewrites text, not symlinks or ELF RPATHs.
# Make host-internal absolute symlinks relative, reject build-tree escape
# links, and verify no ELF RPATH still refers to the original host tree.
python3 - "$host" "$output" "$source_dir" "$PATCHELF" <<'PY'
from pathlib import Path
import os
import subprocess
import sys
root = Path(sys.argv[1])
output, source, patchelf = sys.argv[2:]
for path in root.rglob('*'):
    if path.is_symlink():
        target = os.readlink(path)
        if target.startswith(str(root) + '/'):
            replacement = os.path.relpath(target, path.parent)
            path.unlink()
            path.symlink_to(replacement)
        elif target.startswith(output + '/') or target.startswith(source + '/'):
            raise SystemExit(f'SDK symlink escapes into build sources: {path}: {target}')
        continue
    if not path.is_file():
        continue
    with path.open('rb') as stream:
        if stream.read(4) != b'\x7fELF':
            continue
    result = subprocess.run([patchelf, '--print-rpath', str(path)],
                            capture_output=True, text=True)
    if result.returncode == 0 and str(root) in result.stdout:
        raise SystemExit(f'Absolute build RPATH remains in {path}: {result.stdout}')
PY

install -m 755 "$source_dir/support/misc/relocate-sdk.sh" "$host/relocate-sdk.sh"
mkdir -p "$host/share/buildroot"
# Follow the fixed Buildroot prepare-sdk recipe's text-file selection.
python3 - "$host" <<'PY'
from pathlib import Path
import subprocess
import sys
root = Path(sys.argv[1])
needle = str(root).encode()
metadata = root / 'share/buildroot'
paths = []
for path in root.rglob('*'):
    if path.is_symlink() or not path.is_file() or path in (metadata / 'sdk-location', metadata / 'sdk-relocs'):
        continue
    data = path.read_bytes()
    if needle not in data:
        continue
    mime = subprocess.check_output(['file', '-b', '--mime-type', str(path)], text=True).strip()
    if mime.startswith('text/'):
        paths.append('./' + str(path.relative_to(root)))
(metadata / 'sdk-location').write_text(str(root) + '\n')
(metadata / 'sdk-relocs').write_text('\n'.join(sorted(paths)) + '\n')
PY
cp "$output/.config" "$artifacts/buildroot.config"
archive="$artifacts/tab5-rv32imac-nommu-sdk.tar.gz"
tar --owner=0 --group=0 --numeric-owner -C "$output" -czf "$archive" host

# Prove that the archive can be extracted and relocated, and that the
# relocated wrapper, compiler, libc and elf2flt produce a bFLT executable.
# The original live build tree is neither moved nor modified by this test.
smoke=$(mktemp -d "${output%/*}/sdk-smoke.XXXXXXXX")
tar -xzf "$archive" -C "$smoke"
relocated="$smoke/host"
"$relocated/relocate-sdk.sh" | tee "$artifacts/sdk-relocation.log"
relocated_cc="$relocated/bin/riscv32-buildroot-linux-uclibc-gcc"
sysroot=$("$relocated_cc" -print-sysroot)
libc=$("$relocated_cc" -print-file-name=libc.a)
cc1=$("$relocated_cc" -print-prog-name=cc1)
for sdk_path in "$sysroot" "$libc" "$cc1"; do
    resolved=$(realpath -- "$sdk_path")
    [[ "$resolved" == "$relocated/"* ]] || {
        echo "Relocated SDK still resolves outside its archive: $sdk_path" >&2; exit 1;
    }
    test -e "$resolved"
done
cat > "$smoke/hello.c" <<'EOF'
#include <stdio.h>
int main(void) { puts("Tab5 relocated SDK check"); return 0; }
EOF
"$relocated_cc" -Os -fPIC -static -march=rv32imac_zicsr_zifencei -mabi=ilp32 \
    '-Wl,-elf2flt=-r -s32768' -o "$smoke/hello" "$smoke/hello.c" \
    2>&1 | tee "$artifacts/sdk-compile.log"
python3 - "$smoke/hello" "$sysroot" "$libc" "$cc1" "$artifacts" <<'PY'
import hashlib
import json
from pathlib import Path
import struct
import sys
binary = Path(sys.argv[1])
data = binary.read_bytes()
if len(data) < 64 or data[:4] != b'bFLT':
    raise SystemExit('Relocated SDK did not produce bFLT')
header = struct.unpack('>4s15I', data[:64])
if header[1] != 4 or header[6] < 32768 or header[9] & 0x0c:
    raise SystemExit('Unexpected relocated bFLT revision, stack, or compression')
report = {'relocation_compile': 'passed', 'target_execution': 'not_performed',
          'sysroot': sys.argv[2], 'libc': sys.argv[3], 'cc1': sys.argv[4],
          'bflt_stack_bytes': header[6], 'binary_bytes': len(data),
          'binary_sha256': hashlib.sha256(data).hexdigest()}
(Path(sys.argv[5]) / 'sdk-smoke.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
PY
(cd "$artifacts" && sha256sum tab5-rv32imac-nommu-sdk.tar.gz buildroot.config \
    sdk-smoke.json > SHA256SUMS.txt)
