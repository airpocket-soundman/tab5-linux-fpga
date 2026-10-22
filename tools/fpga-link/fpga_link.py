#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Desktop/Linux CPython mock CLI. No hardware backend is provided."""
import argparse
import json
from pathlib import Path

from codec import ID, ECHO, INVERT, mock_reply, validate_response
from transport import LinkClient, MockTransport


def check_vectors():
    vectors = json.loads((Path(__file__).parent / "vendor/link_vectors.json").read_text())
    for vector in vectors:
        request = bytes.fromhex(vector["request"])
        response = bytes.fromhex(vector["response"])
        if mock_reply(request) != response:
            raise AssertionError("mock reply mismatch: " + vector["name"])
        if validate_response(response, request) != vector["host_accept"]:
            raise AssertionError("host validation mismatch: " + vector["name"])
    return len(vectors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true", required=True,
                        help="required: no physical transport is implemented")
    parser.add_argument("--fragment-size", type=int, choices=range(1, 9), default=8)
    parser.add_argument("command", choices=("id", "echo", "invert", "selftest"))
    parser.add_argument("payload", nargs="*", type=lambda value: int(value, 0))
    args = parser.parse_args()
    expected = 2 if args.command in ("echo", "invert") else 0
    if len(args.payload) != expected or any(not 0 <= v <= 255 for v in args.payload):
        parser.error("id/selftest take no payload; echo/invert take two uint8 values")
    client = LinkClient(MockTransport(args.fragment_size))
    if args.command == "selftest":
        count = check_vectors()
        client.transfer(ID)
        for value in range(256):
            client.transfer(ECHO, value, value ^ 0xa5)
            client.transfer(INVERT, value, 255 - value)
        result = {"golden_vectors": count, "mock_transactions": 513}
    else:
        result = client.transfer({"id": ID, "echo": ECHO, "invert": INVERT}[args.command],
                                 *args.payload)
    print(json.dumps({"backend": "mock", "physical_link_tested": False, **result}))


if __name__ == "__main__":
    main()
