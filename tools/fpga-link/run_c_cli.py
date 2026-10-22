#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compile the portable C mock CLI and compare all 583 golden vectors."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from codec import ID, ECHO, INVERT, make_request, mock_reply, validate_response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", required=True)
    parser.add_argument("--zig", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    vectors = json.loads((root / "vendor/link_vectors.json").read_text())
    with tempfile.TemporaryDirectory(prefix="fpga-link-c-cli-") as temp:
        executable = Path(temp) / "fpga-link.exe"
        command = [args.cc] + (["cc"] if args.zig else [])
        subprocess.run(command + ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                                  str(root / "fpga_link.c"), "-o", str(executable)], check=True)

        def run(arguments, data=None, expected_code=0):
            result = subprocess.run([str(executable)] + arguments, input=data,
                                    capture_output=True, timeout=30)
            if result.returncode != expected_code:
                raise AssertionError((arguments, result.returncode, result.stderr.decode()))
            return result.stdout

        def assert_mock(result):
            assert result["backend"] == "mock"
            assert result["physical_link_tested"] is False

        data = "".join(v["request"] + "\n" for v in vectors).encode("ascii")
        replies = run(["--mock", "--vectors"], data).splitlines()
        assert len(replies) == len(vectors) == 583
        for vector, line in zip(vectors, replies):
            result = json.loads(line)
            assert_mock(result)
            request = bytes.fromhex(vector["request"])
            response = bytes.fromhex(result["response"])
            assert result["request"] == vector["request"], vector["name"]
            assert response == mock_reply(request) == bytes.fromhex(vector["response"]), vector["name"]
            assert result["host_accept"] == validate_response(response, request) == vector["host_accept"], vector["name"]

        for arguments, opcode, first, second in ((["id"], ID, 0, 0),
                (["echo", "0x55", "170"], ECHO, 0x55, 0xaa),
                (["invert", "0", "0xff"], INVERT, 0, 255)):
            result = json.loads(run(["--mock"] + arguments))
            assert_mock(result)
            request = make_request(opcode, 0, first, second)
            assert result["request"] == request.hex()
            assert result["response"] == mock_reply(request).hex()

        result = json.loads(run(["--mock", "selftest"]))
        assert_mock(result)
        assert result["mock_transactions"] == 513
        rejected = ([], ["id"], ["--device", "id"], ["--mock", "id", "1"],
                    ["--mock", "echo", "0"], ["--mock", "echo", "256", "0"],
                    ["--mock", "echo", "-1", "0"], ["--mock", "echo", "0x", "0"],
                    ["--mock", "echo", "1.0", "0"], ["--mock", "echo", "999999999999", "0"],
                    ["--mock", "unknown"])
        for arguments in rejected:
            run(arguments, expected_code=2)
        for bad in (b"00\n", b"zzzzzzzzzzzzzzzz\n", b"0" * 64 + b"\n"):
            run(["--mock", "--vectors"], bad, expected_code=2)
        print(f"C CLI: {len(vectors)} vectors, 513 selftest transactions, "
              f"3 commands, {len(rejected) + 3} rejected inputs: PASS")


if __name__ == "__main__":
    main()
