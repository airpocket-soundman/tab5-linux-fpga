#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build and validate the tmpfile-only C memory probe. Never accesses hardware."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zlib

SIZES = (1, 31, 32, 33, 4097, 65539)
LIMITS = (1, 31, 4096)


def reference_crc(size, seed):
    crc = 0
    for start in range(0, size, 997):
        block = bytearray()
        for position in range(start, min(size, start + 997)):
            x = position ^ seed
            x ^= x >> 16
            x = x * 0x7feb352d & 0xffffffff
            x ^= x >> 15
            x = x * 0x846ca68b & 0xffffffff
            x ^= x >> 16
            block.append(x & 255)
        crc = zlib.crc32(block, crc)
    return f"{crc:08x}"


def execute(command, timeout=60):
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout)


def diagnostic(result):
    return f"exit={result.returncode}\n{result.stderr[-3000:]}{result.stdout[-1000:]}"


def check_success(result, size, limit):
    if result.returncode:
        raise ValueError(f"probe failed for size={size}, limit={limit}: {diagnostic(result)}")
    if result.stderr.strip():
        raise ValueError(f"probe emitted unexpected diagnostics: {diagnostic(result)}")
    output = json.loads(result.stdout)
    if not isinstance(output, dict):
        raise ValueError("probe output must be a JSON object")
    for name, expected in (("bytes_verified", size * 2), ("bytes_per_pass", size),
                           ("chunk", limit), ("working_buffer_bytes", 65536), ("verified_passes", 2)):
        if type(output.get(name)) is not int or output[name] != expected:
            raise ValueError(f"wrong {name}: {output.get(name)!r}, expected {expected}")
    if output.get("physical_link_tested") is not False:
        raise ValueError("probe must report physical_link_tested:false")
    if output.get("mock") is not True:
        raise ValueError("probe must report mock:true")
    values = []
    for name, seed in (("crc32_pass1", 0x9e3779b9), ("crc32_pass2", 0x85ebca6b)):
        actual = output.get(name)
        if not isinstance(actual, str) or re.fullmatch("[0-9a-f]{8}", actual) is None or actual != reference_crc(size, seed):
            raise ValueError(f"probe {name} mismatch for size={size}: {actual!r}")
        values.append(actual)
    return values


def check_failure(result, description, expected_code):
    if result.returncode != expected_code:
        raise ValueError(f"{description} expected exit {expected_code}: {diagnostic(result)}")
    if result.stdout.strip():
        raise ValueError(f"{description} must not print success output")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", required=True, help="existing host C compiler")
    parser.add_argument("--zig", action="store_true")
    parser.add_argument("--sanitize", action="store_true",
                        help="require AddressSanitizer and UndefinedBehaviorSanitizer support")
    args = parser.parse_args()
    source = Path(__file__).resolve().with_name("file_probe.c")
    if not source.is_file():
        parser.error(f"probe source is missing: {source}")
    compiler = shutil.which(args.cc)
    if compiler is None:
        parser.error(f"compiler unavailable: {args.cc}")
    try:
        with tempfile.TemporaryDirectory(prefix="fpga-file-probe-") as temporary:
            binary = Path(temporary) / "file-probe.exe"
            command = [compiler] + (["cc"] if args.zig else [])
            command += ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror"]
            if args.sanitize:
                command += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-sanitize-recover=all"]
            compiled = execute(command + [str(source), "-o", str(binary)])
            if compiled.returncode:
                raise ValueError(f"host compilation failed; requested sanitizers are never silently disabled:\n{diagnostic(compiled)}")
            cases = []
            for size in SIZES:
                for limit in LIMITS:
                    result = execute([str(binary), "--mock", "--size", str(size), "--chunk", str(limit)])
                    cases.append({"size": size, "chunk": limit,
                                  "crc32_passes": check_success(result, size, limit)})
            invalid = ([], ["--size", "1"], ["--mock", "--size", "0"],
                       ["--mock", "--size", "-1"], ["--mock", "--size", "1x"],
                       ["--mock", "--size", "18446744073709551616"],
                       ["--mock", "--size"], ["--mock", "--unknown"],
                       ["--mock", "--chunk", "0"], ["--mock", "--chunk", "65537"],
                       ["--mock", "--chunk", "-1"],
                       ["--mock", "--chunk", "18446744073709551616"],
                       ["--mock", "--size", "1", "--inject-corruption", "1"])
            for options in invalid:
                check_failure(execute([str(binary), *options]), f"invalid CLI {options}", 2)
            for size in (1, 33, 4097):
                corrupted = execute([str(binary), "--mock", "--size", str(size),
                                     "--chunk", "31", "--inject-corruption", str(size - 1)])
                check_failure(corrupted, f"injected corruption at size={size}", 1)
                if f"mock mismatch: pass 1, byte {size - 1}" not in corrupted.stderr:
                    raise ValueError(f"corruption was not detected at the injected address: {diagnostic(corrupted)}")
        print(json.dumps({"kind": "host_file_probe_conformance", "physical_link_tested": False,
                          "performance_measured": False, "sanitizers_requested": args.sanitize,
                          "cases_passed": len(cases), "invalid_inputs_rejected": len(invalid),
                          "corruptions_rejected": 3, "cases": cases}, indent=2))
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"file probe verification failed: {error}\n")


if __name__ == "__main__":
    main()
