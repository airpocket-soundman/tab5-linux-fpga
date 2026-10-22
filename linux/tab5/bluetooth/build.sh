#!/usr/bin/env bash
# Build the libc-only host using the project's relocated RV32 NOMMU SDK.
set -euo pipefail
[[ $# == 2 ]] || { echo 'Usage: build.sh SDK_DIRECTORY OUTPUT_DIRECTORY' >&2; exit 2; }
sdk=$(cd "$1" && pwd)
mkdir -p "$2"
output=$(cd "$2" && pwd)
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
compilers=("$sdk"/bin/*-gcc)
[[ ${#compilers[@]} == 1 && -x ${compilers[0]} ]] || { echo 'Expected one SDK C compiler' >&2; exit 1; }
compiler=${compilers[0]}
[[ $("$compiler" -dumpmachine) == riscv32-* ]] || { echo 'Requires the RV32 NOMMU SDK' >&2; exit 1; }
"$compiler" -Os -std=c11 -fPIC -static -march=rv32imac_zicsr_zifencei \
    -mabi=ilp32 -Wall -Wextra -Werror '-Wl,-elf2flt=-r -s65536' \
    "$here/tab5-ble-hid.c" -o "$output/tab5-ble-hid"
python3 - "$output/tab5-ble-hid" <<'PY'
from pathlib import Path
import struct, sys
b = Path(sys.argv[1]).read_bytes()
if b[:4] != b'bFLT' or struct.unpack_from('>I', b, 4)[0] != 4:
    raise SystemExit('Expected bFLT revision 4')
if struct.unpack_from('>I', b, 24)[0] != 65536:
    raise SystemExit('Wrong stack size')
print('bFLT binary:', len(b), 'bytes; stack 65536 bytes')
PY
(cd "$output" && sha256sum tab5-ble-hid > SHA256SUMS.txt)
