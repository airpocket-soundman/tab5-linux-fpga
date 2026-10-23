# SPDX-License-Identifier: GPL-2.0-only
"""Host-only external object memory model. No wire protocol or device I/O."""
from dataclasses import dataclass
import tempfile


def natural(value, name, positive=False):
    if type(value) is not int or value < (1 if positive else 0):
        raise ValueError(f"{name} must be a {'positive' if positive else 'nonnegative'} integer")
    return value


def check_range(offset, length, capacity):
    natural(offset, "offset")
    natural(length, "length")
    if offset > capacity or length > capacity - offset:
        raise ValueError("range outside object")


@dataclass(frozen=True, eq=False)
class Handle:
    number: int
    size: int


class MockObjectMemory:
    """Synchronous file-backed mock, with bounded individual transfers.

    Handles belong to one instance and become invalid on free/close. Allocation
    uses first fit; fragmentation can reject an allocation despite free space.
    New objects are zeroed. Failure during a multi-tile operation can leave a
    partial result: no atomicity, concurrent access or retry contract is offered.
    """
    def __init__(self, capacity=128 * 1024 * 1024, transfer_limit=4096):
        self.capacity = natural(capacity, "capacity", True)
        self.transfer_limit = natural(transfer_limit, "transfer_limit", True)
        self._file = tempfile.TemporaryFile()
        self._file.truncate(capacity)
        self._free = [(0, capacity)]
        self._objects = {}
        self._serial = 0
        self.peak_transfer = 0
        self.read_transfers = 0
        self.write_transfers = 0
        self.bytes_read = 0
        self.bytes_written = 0
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self._file.close()
        self._objects.clear()
        self._closed = True

    def _open(self):
        if self._closed:
            raise ValueError("memory is closed")

    def _resolve(self, handle):
        self._open()
        if not isinstance(handle, Handle) or handle not in self._objects:
            raise ValueError("unknown, foreign or freed handle")
        return self._objects[handle]

    def allocate(self, size):
        self._open()
        natural(size, "size", True)
        for index, (address, available) in enumerate(self._free):
            if size <= available:
                # Clear before publishing or changing allocator state.
                zeros = bytes(min(size, self.transfer_limit))
                for offset in range(0, size, self.transfer_limit):
                    self._write_at(address + offset, zeros[:min(len(zeros), size - offset)])
                self._free[index:index + 1] = ([(address + size, available - size)]
                                               if available > size else [])
                self._serial += 1
                handle = Handle(self._serial, size)
                self._objects[handle] = address
                return handle
        raise MemoryError("no contiguous extent available")

    def free(self, handle):
        address = self._resolve(handle)
        del self._objects[handle]
        extents = sorted(self._free + [(address, handle.size)])
        self._free = []
        for start, size in extents:
            if self._free and sum(self._free[-1]) == start:
                previous, count = self._free[-1]
                self._free[-1] = (previous, count + size)
            else:
                self._free.append((start, size))

    def _write_at(self, address, data):
        self.peak_transfer = max(self.peak_transfer, len(data))
        self._file.seek(address)
        if self._file.write(data) != len(data):
            raise OSError("short mock write")
        self.write_transfers += 1
        self.bytes_written += len(data)

    def read(self, handle, offset, length):
        address = self._resolve(handle)
        check_range(offset, length, handle.size)
        if length > self.transfer_limit:
            raise ValueError("transfer exceeds limit; use tiles")
        self.peak_transfer = max(self.peak_transfer, length)
        self._file.seek(address + offset)
        data = self._file.read(length)
        if len(data) != length:
            raise OSError("short mock read")
        self.read_transfers += 1
        self.bytes_read += length
        return data

    def write(self, handle, offset, data):
        address = self._resolve(handle)
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("data must be bytes or bytearray")
        check_range(offset, len(data), handle.size)
        if len(data) > self.transfer_limit:
            raise ValueError("transfer exceeds limit; use tiles")
        self._write_at(address + offset, data)

    def tiles(self, handle, offset=0, length=None):
        self._resolve(handle)
        length = handle.size - offset if length is None else length
        check_range(offset, length, handle.size)
        for position in range(offset, offset + length, self.transfer_limit):
            yield position, self.read(handle, position, min(self.transfer_limit, offset + length - position))

    def copy(self, source, source_offset, target, target_offset, length):
        self._resolve(source)
        self._resolve(target)
        check_range(source_offset, length, source.size)
        check_range(target_offset, length, target.size)
        # memmove semantics even for an overlapping range within one object.
        backward = source is target and source_offset < target_offset < source_offset + length
        remaining = length
        consumed = 0
        while remaining:
            count = min(remaining, self.transfer_limit)
            relative = remaining - count if backward else consumed
            data = self.read(source, source_offset + relative, count)
            self.write(target, target_offset + relative, data)
            remaining -= count
            consumed += count


MAX_EXPERIMENT_SIZE = 128 * 1024 * 1024
MAX_EXPERIMENT_TRANSFER = 1024 * 1024


def demo(size=1024 * 1024 + 17, transfer_limit=4096):
    """Spill generated tiles, restore into another object, process one tile at a time."""
    import hashlib
    import json
    import zlib
    natural(size, "size", True)
    natural(transfer_limit, "transfer_limit", True)
    if size > MAX_EXPERIMENT_SIZE or transfer_limit > MAX_EXPERIMENT_TRANSFER:
        raise ValueError("experiment size exceeds 128 MiB or transfer limit exceeds 1 MiB")
    pattern = bytes(range(251))
    with MockObjectMemory(capacity=2 * size, transfer_limit=transfer_limit) as memory:
        source = memory.allocate(size)
        restored = memory.allocate(size)
        expected = hashlib.sha256()
        for offset in range(0, size, memory.transfer_limit):
            count = min(memory.transfer_limit, size - offset)
            phase = offset % 251
            data = (pattern * ((count + phase + 250) // 251))[phase:phase + count]
            memory.write(source, offset, data)
            expected.update(data)
        memory.copy(source, 0, restored, 0, size)
        actual = hashlib.sha256()
        byte_sum = 0
        crc = 0
        for _, data in memory.tiles(restored):
            actual.update(data)
            byte_sum += sum(data)
            crc = zlib.crc32(data, crc)
        if actual.digest() != expected.digest():
            raise AssertionError("restore mismatch")
        print(json.dumps({"backend": "host-file-mock", "physical_link_tested": False,
                          "bytes_verified": size, "transfer_limit": memory.transfer_limit,
                          "readback_crc32": f"{crc:08x}",
                          "peak_transfer": memory.peak_transfer, "sha256": actual.hexdigest(),
                          "tiled_byte_sum": byte_sum, "read_transfers": memory.read_transfers,
                          "write_transfers": memory.write_transfers,
                          "bytes_read": memory.bytes_read, "bytes_written": memory.bytes_written}))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true", required=True)
    parser.add_argument("--size", type=int, default=1024 * 1024 + 17,
                        help="bytes per object, 1..134217728; temporary file capacity is twice this")
    parser.add_argument("--transfer-limit", type=int, default=4096,
                        help="maximum bytes per transfer, 1..1048576")
    args = parser.parse_args()
    if not 1 <= args.size <= MAX_EXPERIMENT_SIZE:
        parser.error("--size must be in 1..134217728")
    if not 1 <= args.transfer_limit <= MAX_EXPERIMENT_TRANSFER:
        parser.error("--transfer-limit must be in 1..1048576")
    demo(args.size, args.transfer_limit)
