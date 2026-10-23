#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check an uncompressed bFLT v4 executable's static layout; never execute it."""
import argparse
import json
from pathlib import Path
import struct


def check(data):
    if len(data) < 64:
        raise ValueError('truncated bFLT header')
    magic, *fields = struct.unpack('>4s15I', data[:64])
    revision, entry, data_start, data_end, bss_end, stack, reloc_start, reloc_count, flags = fields[:9]
    if magic != b'bFLT' or revision != 4:
        raise ValueError('expected bFLT revision 4')
    if flags & 0x0c:
        raise ValueError('compressed bFLT layout is not supported by this checker')
    if not (64 <= entry < data_start <= data_end <= bss_end):
        raise ValueError('invalid text/data/BSS bounds')
    if data_end > len(data) or reloc_start < data_end:
        raise ValueError('data/relocations extend outside the file')
    if reloc_start > len(data) or reloc_count > (len(data) - reloc_start) // 4:
        raise ValueError('truncated relocation records')
    if stack != 32768:
        raise ValueError('expected explicitly configured 32768-byte stack')
    return {'kind':'bFLT_static_layout','revision':revision,'entry':entry,
            'initialized_bytes':data_end,'bss_bytes':bss_end-data_end,
            'requested_stack_bytes':stack,'relocations':reloc_count,
            'target_runtime_tested':False,'physical_link_tested':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('binary',type=Path)
    a=p.parse_args()
    try:
        print(json.dumps(check(a.binary.read_bytes()),indent=2))
    except (OSError,ValueError) as e:
        p.error(str(e))


if __name__=='__main__': main()
