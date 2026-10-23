#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compare host-only Linux/MeOS memory demos against an independent CRC reference."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zlib

SIZES = (1, 31, 32, 33, 4097, 65539)
LIMITS = (31, 4096)


def checked_run(command, *, timeout=30):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {command[0]}\n"
                           f"{result.stderr[-4000:]}{result.stdout[-1000:]}")
    return result.stdout


def expected_crc(size):
    # Deliberately independent of both implementations and their transfer limits.
    crc = 0
    for start in range(0, size, 997):
        crc = zlib.crc32(bytes(index % 251 for index in range(start, min(size, start + 997))), crc)
    return f"{crc:08x}"


def validate(label, output, size, limit, crc):
    result = json.loads(output)
    if not isinstance(result, dict):
        raise ValueError(f"{label}: expected a JSON object")
    for field, expected in (("bytes_verified", size), ("transfer_limit", limit)):
        if type(result.get(field)) is not int or result[field] != expected:
            raise ValueError(f"{label}: {field} does not equal {expected}")
    if result.get("physical_link_tested") is not False:
        raise ValueError(f"{label}: physical_link_tested must be false")
    actual = result.get("readback_crc32")
    if not isinstance(actual, str) or re.fullmatch(r"[0-9a-f]{8}", actual) is None or actual != crc:
        raise ValueError(f"{label}: restored data CRC mismatch: expected {crc}, got {actual!r}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meos-root", required=True, type=Path)
    parser.add_argument("--cc", required=True, help="existing host C compiler path or command")
    parser.add_argument("--zig", action="store_true", help="invoke the compiler as zig cc")
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    meos = args.meos_root.resolve() / "experiments" / "fpga-memory"
    sources = [meos / "fpga_memory.c", meos / "demo_memory.c"]
    for path in [here / "memory_mock.py", meos / "fpga_memory.h", *sources]:
        if not path.is_file():
            parser.error(f"required local dependency is absent: {path}; no repository is cloned automatically")
    compiler = shutil.which(args.cc)
    if compiler is None:
        parser.error(f"host compiler is unavailable: {args.cc}")
    try:
        cases = []
        with tempfile.TemporaryDirectory(prefix="fpga-memory-conformance-") as temporary:
            executable = Path(temporary) / "memory-demo.exe"
            checked_run([compiler] + (["cc"] if args.zig else []) +
                        ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                         *map(str, sources), "-o", str(executable)], timeout=120)
            for size in SIZES:
                crc = expected_crc(size)
                for limit in LIMITS:
                    options = ["--mock", "--size", str(size), "--transfer-limit", str(limit)]
                    for label, command in (("Linux Python", [sys.executable, str(here / "memory_mock.py")]),
                                           ("MeOS C host", [str(executable)])):
                        validate(label, checked_run(command + options), size, limit, crc)
                    cases.append({"bytes_verified": size, "transfer_limit": limit, "readback_crc32": crc})
        print(json.dumps({"kind": "cross_implementation_host_conformance", "cases_passed": len(cases),
                          "implementations": ["Linux Python file mock", "MeOS portable C host mock"],
                          "physical_link_tested": False, "linux_runtime_tested": False,
                          "meos_runtime_tested": False, "performance_measured": False,
                          "cases": cases}, indent=2))
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"conformance failed: {error}\n")


if __name__ == "__main__":
    main()
