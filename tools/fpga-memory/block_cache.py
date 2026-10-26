# SPDX-License-Identifier: GPL-2.0-only
"""Synchronous bounded write-through cache for revision-aware host mocks."""
from collections import OrderedDict
from memory_mock import check_range, natural


class BlockCache:
    """Cache immutable full/tail blocks; never keep dirty data.

    backend.describe must reject stale handles and expose a revision advanced
    BEFORE every validated write attempt, including an attempt that then fails.
    No concurrent access or backend mutation during an operation is supported.
    read returns immutable bytes. Assembly and final conversion can transiently
    use up to twice transfer_limit in addition to cached payload, separately
    bounded by block_size * max_blocks. Python metadata is outside that bound.
    """
    def __init__(self, backend, block_size=1024, max_blocks=8):
        natural(block_size, "block_size", True)
        natural(max_blocks, "max_blocks", True)
        natural(backend.transfer_limit, "backend transfer_limit", True)
        if block_size > backend.transfer_limit:
            raise ValueError("block size exceeds backend transfer limit")
        self.backend = backend
        self.block_size = block_size
        self.max_blocks = max_blocks
        self._blocks = OrderedDict()
        self._hits = self._misses = self._reads = self._writes = 0

    @property
    def stats(self):
        """Block hits/misses and attempted backend read/write calls."""
        return {"hits": self._hits, "misses": self._misses,
                "backend_reads": self._reads, "backend_writes": self._writes,
                "resident_blocks": len(self._blocks),
                "resident_bytes": sum(len(value[1]) for value in self._blocks.values()),
                "capacity_bytes": self.block_size * self.max_blocks}

    def clear(self):
        """Drop payload, preserving cumulative counters. No writeback occurs."""
        self._blocks.clear()

    def _drop(self, handle):
        for key in list(self._blocks):
            if key[0] is handle:
                del self._blocks[key]

    def invalidate(self, handle):
        """Discard one object's blocks; reject a freed/foreign/closed handle."""
        try:
            self.backend.describe(handle)
        finally:
            self._drop(handle)

    def _validate(self, handle, offset, length):
        # Validate all caller arguments before touching cache recency/counters.
        natural(offset, "offset")
        natural(length, "length")
        try:
            info = self.backend.describe(handle)
        except Exception:
            self._drop(handle)
            raise
        check_range(offset, length, info["size"])
        if length > self.backend.transfer_limit:
            raise ValueError("transfer exceeds backend limit")
        for key, (revision, _) in list(self._blocks.items()):
            if key[0] is handle and revision != info["revision"]:
                del self._blocks[key]
        return info

    def read(self, handle, offset, length):
        info = self._validate(handle, offset, length)
        result = bytearray(length)
        position = offset
        while position < offset + length:
            start = position // self.block_size * self.block_size
            key = (handle, start)
            if key in self._blocks:
                self._hits += 1
                self._blocks.move_to_end(key)
                data = self._blocks[key][1]
            else:
                self._misses += 1
                if len(self._blocks) == self.max_blocks:
                    self._blocks.popitem(last=False)
                self._reads += 1
                count = min(self.block_size, info["size"] - start)
                data = self.backend.read(handle, start, count)
                if not isinstance(data, bytes) or len(data) != count:
                    raise OSError("backend must return a complete immutable block")
                self._blocks[key] = (info["revision"], data)
            count = min(len(data) - (position - start), offset + length - position)
            result[position - offset:position - offset + count] = memoryview(data)[position - start:position - start + count]
            position += count
        return bytes(result)

    def write(self, handle, offset, data):
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("data must be bytes or bytearray")
        self._validate(handle, offset, len(data))
        self._drop(handle)
        self._writes += 1
        try:
            self.backend.write(handle, offset, data)
        finally:
            # Covers partial writes and future backend implementations that fail.
            self._drop(handle)
