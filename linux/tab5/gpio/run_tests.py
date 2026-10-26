#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build injected GPIO host tests, never Linux adapter or physical GPIO."""
import argparse
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--cc", required=True)
parser.add_argument("--zig", action="store_true")
args = parser.parse_args()
here = Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix="tab5-gpio-test-") as directory:
    binary = Path(directory) / "gpio-test.exe"
    subprocess.run([args.cc, *(["cc"] if args.zig else []), "-std=c11", "-O2",
                    "-Wall", "-Wextra", "-Werror", str(here / "tab5_gpio.c"),
                    str(here / "test_gpio.c"), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
