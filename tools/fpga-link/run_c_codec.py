#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compile/run the existing pure C codec with an explicitly selected host CC."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", required=True)
    parser.add_argument("--zig", action="store_true", help="invoke the compiler as zig cc")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    vectors = json.loads((root / "vendor/link_vectors.json").read_text())
    records = "".join(f'{v["request"]} {v["response"]} {int(v["host_accept"])}\n' for v in vectors)
    with tempfile.TemporaryDirectory(prefix="fpga-link-codec-") as temp:
        executable = Path(temp) / "test_codec.exe"
        command = [args.cc] + (["cc"] if args.zig else [])
        subprocess.run(command + ["-std=c11", "-Wall", "-Wextra", "-Werror",
                                  str(root / "test_codec.c"), "-o", str(executable)], check=True)
        subprocess.run([str(executable)], input=records.encode("ascii"), check=True)


if __name__ == "__main__":
    main()
