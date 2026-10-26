#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Linux-only GPIO adapter tests; every device syscall is replaced by a fake."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--cc", required=True)
parser.add_argument("--zig", action="store_true")
parser.add_argument("--sanitize", action="store_true")
args = parser.parse_args()
if sys.platform != "linux":
    parser.error("Linux headers/runtime are required; this runner never accesses GPIO devices")
here = Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix="tab5-gpio-adapter-test-") as directory:
    binary = Path(directory) / "gpio-adapter-test"
    command = [args.cc, *(["cc"] if args.zig else []), "-std=c11", "-O2",
               "-Wall", "-Wextra", "-Werror"]
    if args.sanitize:
        command += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-sanitize-recover=all"]
    subprocess.run([*command, str(here / "test_linux_adapter.c"), "-o", str(binary)], check=True, timeout=120)
    subprocess.run([str(binary)], check=True, timeout=30)
