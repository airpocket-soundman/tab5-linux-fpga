# SPDX-License-Identifier: GPL-2.0-only
import unittest
from memory_mock import Handle, MockObjectMemory


class RevisionTests(unittest.TestCase):
    def setUp(self):
        self.memory=MockObjectMemory(1024,16)
        self.addCleanup(self.memory.close)
        self.handle=self.memory.allocate(33)

    def test_describe_is_live_detached_metadata(self):
        info=self.memory.describe(self.handle)
        self.assertEqual(info,{'size':33,'revision':0})
        info['size']=999
        info['revision']=999
        self.assertEqual(self.memory.describe(self.handle),{'size':33,'revision':0})
        self.memory.read(self.handle,0,4)
        self.assertEqual(self.memory.describe(self.handle)['revision'],0)

    def test_successful_and_failed_attempts_revoke_old_content(self):
        other=self.memory.allocate(3)
        self.memory.write(self.handle,0,b'abcd')
        self.assertEqual(self.memory.describe(self.handle)['revision'],1)
        original=self.memory._write_at
        def partial(address,data):
            original(address,data[:1])
            raise OSError('fault after partial write')
        self.memory._write_at=partial
        with self.assertRaises(OSError): self.memory.write(self.handle,0,b'xyz')
        self.memory._write_at=original
        self.assertEqual(self.memory.describe(self.handle)['revision'],2)
        self.assertEqual(self.memory.describe(other)['revision'],0)
        self.assertEqual(self.memory.read(self.handle,0,4),b'xbcd')

    def test_invalid_requests_do_not_change_revision(self):
        for offset,data in [(-1,b'x'),(33,b'x'),(0,bytes(17)),(True,b'x'),(0,'text')]:
            with self.subTest(offset=offset,data=data),self.assertRaises((ValueError,TypeError)):
                self.memory.write(self.handle,offset,data)
        self.assertEqual(self.memory.describe(self.handle)['revision'],0)

    def test_tiled_copy_revises_only_written_target(self):
        target=self.memory.allocate(33)
        self.memory.copy(self.handle,0,target,0,33)
        self.assertEqual(self.memory.describe(target)['revision'],3)
        self.assertEqual(self.memory.describe(self.handle)['revision'],0)

    def test_freed_foreign_forged_and_closed_are_invalid(self):
        forged=Handle(self.handle.number,self.handle.size)
        with MockObjectMemory(64) as other:
            foreign=other.allocate(33)
            for bad in (forged,foreign,None,1):
                with self.assertRaises(ValueError): self.memory.describe(bad)
        self.memory.free(self.handle)
        replacement=self.memory.allocate(33)
        self.assertEqual(self.memory.describe(replacement)['revision'],0)
        with self.assertRaises(ValueError): self.memory.describe(self.handle)
        self.memory.close()
        with self.assertRaises(ValueError): self.memory.describe(replacement)


if __name__=='__main__': unittest.main()
