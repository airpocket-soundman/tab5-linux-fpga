#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Deterministic host mock cache comparison; no device or timing measurements."""
import argparse
import hashlib
import json

from memory_mock import MockObjectMemory

SIZE = 65539
TRANSFER_LIMIT = 4096
BLOCK_SIZE = 256
MAX_BLOCKS = 8
REPEATS = 16
WINDOWS = ((13, 97), (239, 97), (600, 97), (SIZE - 23, 23))


def pattern(offset, length):
    # Data depends on both low and high address bits, unlike a repeating byte ramp.
    return bytes((address % 251) ^ ((address // 251) % 256)
                 for address in range(offset, offset + length))


def run(use_cache):
    from block_cache import BlockCache
    with MockObjectMemory(capacity=SIZE, transfer_limit=TRANSFER_LIMIT) as backend:
        handle = backend.allocate(SIZE)
        for offset in range(0, SIZE, TRANSFER_LIMIT):
            backend.write(handle, offset, pattern(offset, min(TRANSFER_LIMIT, SIZE - offset)))
        reader = BlockCache(backend, block_size=BLOCK_SIZE, max_blocks=MAX_BLOCKS) if use_cache else backend
        digest = hashlib.sha256()
        bytes_returned = 0
        start_calls, start_bytes = backend.read_transfers, backend.bytes_read
        cold_calls = None
        for repetition in range(REPEATS):
            for offset, length in WINDOWS:
                actual = reader.read(handle, offset, length)
                if actual != pattern(offset, length):
                    raise ValueError(f"read mismatch at offset {offset}, cached={use_cache}")
                digest.update(actual)
                bytes_returned += len(actual)
            if repetition == 0:
                cold_calls = backend.read_transfers - start_calls
        result = {"sha256": digest.hexdigest(), "bytes_returned": bytes_returned,
                  "window_requests": REPEATS * len(WINDOWS),
                  "backend_read_requests": backend.read_transfers - start_calls,
                  "backend_read_bytes": backend.bytes_read - start_bytes,
                  "cold_iteration_backend_requests": cold_calls,
                  "remaining_iterations_backend_requests": backend.read_transfers - start_calls - cold_calls}
        if use_cache:
            result["cache_stats"] = reader.stats
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true", required=True)
    parser.parse_args()
    try:
        direct, cached = run(False), run(True)
        if direct["sha256"] != cached["sha256"] or direct["bytes_returned"] != cached["bytes_returned"]:
            raise ValueError("direct/cache results differ")
        if cached["backend_read_requests"] >= direct["backend_read_requests"]:
            raise ValueError("repeated-window workload did not reduce backend requests")
        print(json.dumps({"kind": "host_mock_repeated_window_comparison", "physical_link_tested": False,
                          "performance_measured": False, "linux_runtime_tested": False,
                          "object_bytes": SIZE, "transfer_limit": TRANSFER_LIMIT,
                          "block_size": BLOCK_SIZE, "max_blocks": MAX_BLOCKS,
                          "payload_capacity_bytes": BLOCK_SIZE * MAX_BLOCKS,
                          "repeats": REPEATS, "windows": WINDOWS,
                          "identical_bytes_verified": True, "direct": direct, "cached": cached,
                          "note": "Backend request counts for this workload only; not timing, RAM usage or FPGA performance."}, indent=2))
    except (ImportError, OSError, ValueError) as error:
        parser.exit(1, f"cache comparison failed: {error}\n")


if __name__ == "__main__":
    main()
