# SPDX-License-Identifier: GPL-2.0-only
import random
import unittest
from memory_mock import Handle, MockObjectMemory


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.memory = MockObjectMemory(4096, 31)
        self.addCleanup(self.memory.close)

    def test_spill_restore_tiled(self):
        source = self.memory.allocate(1027)
        target = self.memory.allocate(1027)
        expected = bytes(i % 251 for i in range(1027))
        for offset in range(0, 1027, 31):
            self.memory.write(source, offset, expected[offset:offset + 31])
        self.memory.copy(source, 0, target, 0, 1027)
        self.assertEqual(b"".join(data for _, data in self.memory.tiles(target)), expected)
        self.assertLessEqual(self.memory.peak_transfer, 31)

    def test_range_and_transfer_rejection_preserves_data(self):
        handle = self.memory.allocate(50)
        self.memory.write(handle, 0, b"abc")
        for offset, length in [(-1, 1), (0, -1), (51, 0), (49, 2), (2**64, 1), (True, 1), (0, 32)]:
            with self.assertRaises(ValueError):
                self.memory.read(handle, offset, length)
        for offset, data in [(50, b"x"), (-1, b"x"), (0, bytes(32))]:
            with self.assertRaises(ValueError):
                self.memory.write(handle, offset, data)
        self.assertEqual(self.memory.read(handle, 0, 3), b"abc")
        self.assertEqual(self.memory.read(handle, 50, 0), b"")

    def test_free_coalesces_and_clears_reused_extent(self):
        first, second = self.memory.allocate(2000), self.memory.allocate(2096)
        self.memory.write(first, 0, b"secret")
        with self.assertRaises(MemoryError):
            self.memory.allocate(1)
        self.memory.free(first)
        self.memory.free(second)
        whole = self.memory.allocate(4096)
        self.assertEqual(self.memory.read(whole, 0, 6), bytes(6))

    def test_foreign_forged_stale_closed_handles(self):
        handle = self.memory.allocate(10)
        with MockObjectMemory(100) as other:
            foreign = other.allocate(10)
            for bad in [foreign, Handle(handle.number, handle.size), 1, None]:
                with self.assertRaises(ValueError):
                    self.memory.read(bad, 0, 1)
        self.memory.free(handle)
        self.memory.allocate(10)
        with self.assertRaises(ValueError):
            self.memory.free(handle)
        self.memory.close()
        with self.assertRaises(ValueError):
            self.memory.allocate(1)

    def test_overlapping_copy_matches_memmove(self):
        rng = random.Random(20261023)
        handle = self.memory.allocate(257)
        for _ in range(150):
            expected = bytearray(rng.randbytes(257))
            for offset in range(0, 257, 31):
                self.memory.write(handle, offset, expected[offset:offset + 31])
            length = rng.randrange(258)
            source = rng.randrange(258 - length)
            target = rng.randrange(258 - length)
            expected[target:target + length] = expected[source:source + length]
            self.memory.copy(handle, source, handle, target, length)
            self.assertEqual(b"".join(data for _, data in self.memory.tiles(handle)), expected)

    def test_invalid_allocation_and_construction(self):
        for value in [0, -1, True, 1.5]:
            with self.assertRaises(ValueError):
                self.memory.allocate(value)
            with self.assertRaises(ValueError):
                MockObjectMemory(value)
            with self.assertRaises(ValueError):
                MockObjectMemory(100, value)

    def test_invalid_copy_checked_before_mutation(self):
        handle = self.memory.allocate(10)
        self.memory.write(handle, 0, b"0123456789")
        with self.assertRaises(ValueError):
            self.memory.copy(handle, 0, handle, 8, 3)
        self.assertEqual(self.memory.read(handle, 0, 10), b"0123456789")

    def test_copy_fault_is_visible_and_not_retried(self):
        source, target = self.memory.allocate(70), self.memory.allocate(70)
        for offset in range(0, 70, 31):
            self.memory.write(source, offset, bytes([17]) * min(31, 70 - offset))
        original = self.memory._write_at
        calls = []

        def fail_second(address, data):
            calls.append(address)
            if len(calls) == 2:
                raise TimeoutError("injected host fault")
            original(address, data)

        self.memory._write_at = fail_second
        with self.assertRaises(TimeoutError):
            self.memory.copy(source, 0, target, 0, 70)
        self.assertEqual(len(calls), 2)
        self.memory._write_at = original
        self.assertEqual(self.memory.read(target, 0, 31), bytes([17]) * 31)
        self.assertEqual(self.memory.read(target, 31, 31), bytes(31))
        # Explicit full retry is safe for this separate-object copy.
        self.memory.copy(source, 0, target, 0, 70)
        self.assertEqual(b"".join(data for _, data in self.memory.tiles(target)), bytes([17]) * 70)

    def test_failed_allocation_does_not_publish_or_consume_space(self):
        original = self.memory._write_at

        def fail(address, data):
            raise OSError("injected storage error")

        self.memory._write_at = fail
        with self.assertRaises(OSError):
            self.memory.allocate(4096)
        self.assertEqual(self.memory._objects, {})
        self.memory._write_at = original
        self.assertEqual(self.memory.allocate(4096).size, 4096)

    def test_close_is_session_reset_and_does_not_revive_handle(self):
        stale = self.memory.allocate(10)
        self.memory.close()
        with MockObjectMemory(4096, 31) as replacement:
            current = replacement.allocate(10)
            self.assertEqual(current.number, stale.number)
            with self.assertRaises(ValueError):
                replacement.read(stale, 0, 1)
            self.assertEqual(replacement.read(current, 0, 10), bytes(10))

    def test_actual_short_file_io_raises_without_success_count(self):
        handle = self.memory.allocate(10)
        self.memory.write(handle, 0, b"0123456789")
        underlying = self.memory._file

        class ShortFile:
            def seek(self, *args):
                return underlying.seek(*args)

            def read(self, size):
                return underlying.read(max(0, size - 1))

            def write(self, data):
                return underlying.write(data[:-1])

            def close(self):
                underlying.close()

        reads, writes = self.memory.read_transfers, self.memory.write_transfers
        self.memory._file = ShortFile()
        with self.assertRaises(OSError):
            self.memory.read(handle, 0, 10)
        with self.assertRaises(OSError):
            self.memory.write(handle, 0, b"abcdefghij")
        self.assertEqual((self.memory.read_transfers, self.memory.write_transfers), (reads, writes))
        self.memory._file = underlying
        # A short write has changed storage despite not being confirmed.
        self.assertEqual(self.memory.read(handle, 0, 10), b"abcdefghi9")


    def test_overlap_fault_cannot_be_repaired_by_blind_full_retry(self):
        with MockObjectMemory(10, 3) as memory:
            handle = memory.allocate(10)
            original_data = b"abcdefghij"
            for offset in range(0, 10, 3):
                memory.write(handle, offset, original_data[offset:offset + 3])
            original_write = memory._write_at
            calls = []

            def fail_second(address, data):
                calls.append(address)
                if len(calls) == 2:
                    raise TimeoutError("injected overlap fault")
                original_write(address, data)

            memory._write_at = fail_second
            with self.assertRaises(TimeoutError):
                memory.copy(handle, 0, handle, 1, 8)
            self.assertEqual(len(calls), 2)
            memory._write_at = original_write
            memory.copy(handle, 0, handle, 1, 8)
            actual = b"".join(data for _, data in memory.tiles(handle))
            expected = bytearray(original_data)
            expected[1:9] = original_data[0:8]
            self.assertNotEqual(actual, expected)

    def test_seeded_allocator_state_machine_against_independent_contents(self):
        rng = random.Random(0x20261023)
        expected = {}
        failed_allocations = 0
        frees = 0
        writes = 0
        copies = 0
        for step in range(1000):
            operation = rng.randrange(100)
            handles = list(expected)
            if not handles or operation < 35:
                size = 4097 if step % 23 == 0 else rng.randint(1, 700)
                try:
                    handle = self.memory.allocate(size)
                except MemoryError:
                    failed_allocations += 1
                else:
                    self.assertNotIn(handle, expected)
                    expected[handle] = bytearray(size)
                    self.assertLessEqual(sum(len(data) for data in expected.values()), 4096)
            elif operation < 55:
                handle = rng.choice(handles)
                self.memory.free(handle)
                del expected[handle]
                frees += 1
                with self.assertRaises(ValueError):
                    self.memory.read(handle, 0, 0)
            elif operation < 80:
                handle = rng.choice(handles)
                count = rng.randint(0, min(31, len(expected[handle])))
                offset = rng.randint(0, len(expected[handle]) - count)
                data = rng.randbytes(count)
                self.memory.write(handle, offset, data)
                expected[handle][offset:offset + count] = data
                writes += 1
            else:
                source, target = rng.choice(handles), rng.choice(handles)
                count = rng.randint(0, min(len(expected[source]), len(expected[target])))
                source_offset = rng.randint(0, len(expected[source]) - count)
                target_offset = rng.randint(0, len(expected[target]) - count)
                snapshot = bytes(expected[source][source_offset:source_offset + count])
                self.memory.copy(source, source_offset, target, target_offset, count)
                expected[target][target_offset:target_offset + count] = snapshot
                copies += 1
            # Public reads check every active object after every operation,
            # including failed allocation and updates of neighbouring objects.
            for handle, content in expected.items():
                actual = b"".join(data for _, data in self.memory.tiles(handle))
                self.assertEqual(actual, content, f"step {step}, handle {handle.number}")
        self.assertGreater(failed_allocations, 0)
        self.assertGreater(frees, 0)
        self.assertGreater(writes, 0)
        self.assertGreater(copies, 0)
        for handle in list(expected):
            self.memory.free(handle)
        # Coalescing must recover the complete arena after arbitrary history.
        whole = self.memory.allocate(4096)
        self.assertEqual(b"".join(data for _, data in self.memory.tiles(whole)), bytes(4096))

    def test_mutable_caller_buffer_and_copied_objects_are_independent(self):
        source, target = self.memory.allocate(10), self.memory.allocate(10)
        caller = bytearray(b"0123456789")
        self.memory.write(source, 0, caller)
        caller[:] = b"XXXXXXXXXX"
        self.assertEqual(self.memory.read(source, 0, 10), b"0123456789")
        self.memory.copy(source, 0, target, 0, 10)
        self.memory.write(source, 0, b"abcdefghij")
        self.assertEqual(self.memory.read(target, 0, 10), b"0123456789")
        self.memory.write(target, 0, b"ABCDEFGHIJ")
        self.assertEqual(self.memory.read(source, 0, 10), b"abcdefghij")


if __name__ == "__main__":
    unittest.main()
