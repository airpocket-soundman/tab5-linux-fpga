# SPDX-License-Identifier: GPL-2.0-only
import struct
import unittest
from check_flat import check


def image(**changes):
    values={'revision':4,'entry':64,'data_start':80,'data_end':96,'bss_end':65632,
            'stack':32768,'reloc_start':96,'reloc_count':1,'flags':1}
    values.update(changes)
    fields=[values[k] for k in ('revision','entry','data_start','data_end','bss_end','stack','reloc_start','reloc_count','flags')]
    return struct.pack('>4s15I',b'bFLT',*fields,*([0]*6))+bytes(36)


class FlatTests(unittest.TestCase):
    def test_uncompressed_layout(self):
        r=check(image())
        self.assertEqual(r['bss_bytes'],65536)
        self.assertFalse(r['target_runtime_tested'])

    def test_invalid_header_ranges_and_relocations(self):
        for data in [b'',b'bFLT',b'bad!'+image()[4:],image(revision=3),
                     image(entry=63),image(entry=80),image(data_end=79),
                     image(bss_end=95),image(data_end=101),image(reloc_start=95),
                     image(reloc_start=101),image(reloc_count=2),
                     image(stack=4096),image(flags=4),image(flags=8)]:
            with self.subTest(data=data[:44]),self.assertRaises(ValueError): check(data)


if __name__=='__main__': unittest.main()
