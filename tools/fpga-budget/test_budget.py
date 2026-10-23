# SPDX-License-Identifier: GPL-2.0-only
import unittest
from budget import plan


class BudgetTests(unittest.TestCase):
    def test_documented_resolutions(self):
        for width, height, memory, rate in ((640, 360, 1382400, 13824000),
                                          (720, 1280, 5529600, 55296000)):
            r = plan(width=width, height=height, reserved_bytes=0, stride_bytes=width*2)
            self.assertEqual(r['region_payload_bytes'], memory)
            self.assertEqual(r['required_payload_bps'], rate)
            self.assertFalse(r['physical_link_tested'])

    def test_stride_and_readback_are_distinct(self):
        p = plan(width=3, height=5)
        s = plan(width=3, height=5, readback='strided')
        self.assertEqual(p['stride_bytes'], 64)
        self.assertEqual(p['readback_bytes_per_frame'], 30)
        self.assertEqual(s['readback_bytes_per_frame'], 320)
        self.assertEqual(p['region_payload_bytes'], s['region_payload_bytes'])

    def test_regions_and_alignment(self):
        r = plan(width=1, height=1, reserved_bytes=3, texture_bytes=17)
        regions = r['regions']
        self.assertEqual(regions[0]['offset'], 64)
        for a,b in zip(regions,regions[1:]):
            self.assertLessEqual(a['offset']+a['size'], b['offset'])
        for region in regions:
            self.assertEqual(region['offset'] % 64, 0)
        self.assertEqual(r['used_including_reserved_bytes'] + r['unallocated_bytes'], r['capacity_bytes'])

    def test_capacity_exact_fit_and_one_byte_short(self):
        r = plan(width=640, height=360, reserved_bytes=0)
        cap = r['used_including_reserved_bytes']
        self.assertEqual(plan(capacity_bytes=cap, reserved_bytes=0)['unallocated_bytes'], 0)
        with self.assertRaises(ValueError): plan(capacity_bytes=cap-1, reserved_bytes=0)

    def test_rate_boundary_is_only_payload_budget(self):
        for bps, sufficient in ((13823999,False),(13824000,True),(13824001,True)):
            r=plan(available_readback_bps=bps)
            self.assertEqual(r['payload_budget_sufficient'], sufficient)
            self.assertTrue(r['payload_budget_sufficient_is_not_end_to_end_feasibility'])
        r=plan(available_readback_bps=13824000)
        self.assertEqual(r['readback_only_fps_ceiling'],30)
        self.assertAlmostEqual(r['readback_only_minimum_ms'],1000/30)

    def test_invalid_and_oversized_inputs(self):
        invalid = [{'width':0},{'height':-1},{'capacity_bytes':True},{'fps':False},
                   {'color_buffers':17},{'depth':1},{'reserved_bytes':-1},
                   {'width':1.5},{'texture_bytes':True},{'stride_bytes':1},
                   {'stride_bytes':1279},{'stride_bytes':1281},
                   {'reserved_bytes':2**40},{'width':2**62},
                   {'height':2**62},{'texture_bytes':2**62},
                   {'available_readback_bps':0},{'available_readback_bps':True},
                   {'readback':'physical'},{'available_readback_bps':10**400},
                   {'capacity_bytes':10**400},{'fps':10**400}]
        for args in invalid:
            with self.subTest(args=args),self.assertRaises(ValueError): plan(**args)

    def test_single_color_no_depth_no_textures(self):
        r=plan(color_buffers=1, depth=False)
        self.assertEqual([x['name'] for x in r['regions']], ['color-0'])
        self.assertIsNone(r['depth_format'])


if __name__=='__main__': unittest.main()
