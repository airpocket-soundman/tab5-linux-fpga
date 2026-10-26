# SPDX-License-Identifier: GPL-2.0-only
import random
import unittest
from block_cache import BlockCache
from memory_mock import MockObjectMemory


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.memory=MockObjectMemory(512,32)
        self.addCleanup(self.memory.close)
        self.handle=self.memory.allocate(67)
        self.expected=bytes(range(67))
        for offset in range(0,67,32):
            self.memory.write(self.handle,offset,self.expected[offset:offset+32])
        self.cache=BlockCache(self.memory,block_size=8,max_blocks=2)

    def test_repeated_reads_use_one_backend_request(self):
        before=self.memory.read_transfers
        for _ in range(20): self.assertEqual(self.cache.read(self.handle,2,3),b'\x02\x03\x04')
        self.assertEqual(self.memory.read_transfers-before,1)
        self.assertEqual(self.cache.stats['hits'],19)
        self.assertEqual(self.cache.stats['misses'],1)

    def test_lru_eviction_promotes_hits(self):
        for offset in [0,8,0,16,0]: self.cache.read(self.handle,offset,1)
        self.assertEqual(self.cache.stats['backend_reads'],3)
        self.cache.read(self.handle,8,1)
        self.assertEqual(self.cache.stats['backend_reads'],4)
        self.assertLessEqual(self.cache.stats['resident_bytes'],16)

    def test_unaligned_cross_blocks_and_tail(self):
        for offset,length in [(5,25),(63,4),(67,0),(0,32)]:
            self.assertEqual(self.cache.read(self.handle,offset,length),self.expected[offset:offset+length])
            self.assertLessEqual(self.cache.stats['resident_blocks'],2)
            self.assertLessEqual(self.cache.stats['resident_bytes'],16)
        tail=BlockCache(self.memory,8,1)
        self.assertEqual(tail.read(self.handle,66,1),bytes([66]))
        self.assertEqual(tail.stats['resident_bytes'],3)

    def test_direct_write_and_copy_invalidate_hits(self):
        self.cache.read(self.handle,0,8)
        self.memory.write(self.handle,0,b'changed!')
        self.assertEqual(self.cache.read(self.handle,0,8),b'changed!')
        other=self.memory.allocate(8)
        self.memory.write(other,0,b'new-data')
        self.memory.copy(other,0,self.handle,0,8)
        self.assertEqual(self.cache.read(self.handle,0,8),b'new-data')

    def test_write_through_and_caller_buffer_independence(self):
        self.cache.read(self.handle,0,8)
        data=bytearray(b'updated!')
        self.cache.write(self.handle,0,data)
        data[:]=b'mutated!'
        self.assertEqual(self.memory.read(self.handle,0,8),b'updated!')
        self.assertEqual(self.cache.read(self.handle,0,8),b'updated!')
        self.assertEqual(self.cache.stats['backend_writes'],1)

    def test_partial_write_failure_never_returns_old_cache(self):
        for via_cache in (False,True):
            self.memory.write(self.handle,0,b'abcdefgh')
            self.cache.read(self.handle,0,8)
            original=self.memory._write_at
            def fail(address,data):
                original(address,data[:2])
                raise OSError('partial backend write')
            self.memory._write_at=fail
            try:
                writer=self.cache.write if via_cache else self.memory.write
                with self.assertRaises(OSError): writer(self.handle,0,b'XYZ')
            finally: self.memory._write_at=original
            self.assertEqual(self.cache.read(self.handle,0,8),b'XYcdefgh')

    def test_short_or_failed_block_read_is_not_cached(self):
        original=self.memory.read
        for broken in (lambda *a:b'x',lambda *a:bytearray(8)):
            self.cache.clear()
            self.memory.read=broken
            try:
                with self.assertRaises(OSError): self.cache.read(self.handle,0,3)
            finally: self.memory.read=original
            self.assertEqual(self.cache.stats['resident_blocks'],0)
            self.assertEqual(self.cache.read(self.handle,0,3),bytes(range(3)))
        self.cache.clear()
        def failed(*a): raise OSError('backend unavailable')
        self.memory.read=failed
        try:
            with self.assertRaises(OSError): self.cache.read(self.handle,0,3)
        finally: self.memory.read=original
        self.assertEqual(self.cache.stats['resident_blocks'],0)

    def test_freed_closed_or_foreign_hits_are_rejected(self):
        self.cache.read(self.handle,0,8)
        self.memory.free(self.handle)
        with self.assertRaises(ValueError): self.cache.read(self.handle,0,8)
        self.assertEqual(self.cache.stats['resident_blocks'],0)
        new=self.memory.allocate(67)
        self.cache.read(new,0,8)
        with MockObjectMemory(32) as other:
            with self.assertRaises(ValueError): self.cache.read(other.allocate(8),0,1)
        self.memory.close()
        with self.assertRaises(ValueError): self.cache.read(new,0,8)
        self.assertEqual(self.cache.stats['resident_blocks'],0)

    def test_invalid_requests_leave_cache_and_backend_unchanged(self):
        self.cache.read(self.handle,0,8)
        before=self.cache.stats
        transfers=(self.memory.read_transfers,self.memory.write_transfers)
        for offset,length in [(-1,1),(0,-1),(68,0),(66,2),(0,33),(True,1),(0,False)]:
            with self.assertRaises(ValueError): self.cache.read(self.handle,offset,length)
        for offset,data in [(67,b'x'),(0,bytes(33)),(-1,b'x'),(0,'text')]:
            with self.assertRaises((TypeError,ValueError)): self.cache.write(self.handle,offset,data)
        self.assertEqual(self.cache.stats,before)
        self.assertEqual((self.memory.read_transfers,self.memory.write_transfers),transfers)

    def test_multiple_objects_invalidate_and_clear(self):
        other=self.memory.allocate(8)
        self.cache.read(self.handle,0,1)
        self.cache.read(other,0,1)
        self.cache.invalidate(self.handle)
        self.assertEqual(self.cache.stats['resident_blocks'],1)
        self.cache.clear()
        self.assertEqual(self.cache.stats['resident_bytes'],0)
        self.assertEqual(self.cache.stats['backend_reads'],2)
        self.cache.read(other,0,1)
        self.memory.free(other)
        with self.assertRaises(ValueError): self.cache.invalidate(other)
        self.assertEqual(self.cache.stats['resident_blocks'],0)

    def test_bad_configuration(self):
        for block,count in [(0,1),(1,0),(33,1),(True,1),(1,False),(1.5,1)]:
            with self.assertRaises(ValueError): BlockCache(self.memory,block,count)

    def test_seeded_mixed_reads_writes_against_reference(self):
        rng=random.Random(20261026)
        reference=bytearray(self.expected)
        cache=BlockCache(self.memory,7,3)
        for _ in range(500):
            length=rng.randrange(0,33)
            offset=rng.randrange(0,len(reference)-length+1)
            op=rng.randrange(3)
            if op:
                data=rng.randbytes(length)
                (cache.write if op==1 else self.memory.write)(self.handle,offset,data)
                reference[offset:offset+length]=data
            else:
                self.assertEqual(cache.read(self.handle,offset,length),reference[offset:offset+length])
            self.assertLessEqual(cache.stats['resident_bytes'],21)
        result=b''.join(cache.read(self.handle,i,min(32,67-i)) for i in range(0,67,32))
        self.assertEqual(result,reference)


if __name__=='__main__': unittest.main()
