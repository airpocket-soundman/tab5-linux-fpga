# SPDX-License-Identifier: GPL-2.0-only
import unittest
from ownership import Buffer, Fence, MAX_RANGE, Session


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.session = Session(4096)
        self.color = self.session.register(0, 128)
        self.depth = self.session.register(128, 128)

    def submit(self):
        return self.session.submit(self.color, self.depth, width=8, height=8, stride=16)

    def test_completion_ownership_and_aliases(self):
        alias = self.session.register(2, 16)
        unrelated = self.session.register(512, 16)
        fence = self.submit()
        self.assertEqual(self.session.status(fence), 'pending')
        for handle in (self.color, self.depth, alias):
            for write in (False, True):
                with self.assertRaises(RuntimeError): self.session.cpu_access(handle, write=write)
            with self.assertRaises(RuntimeError): self.session.free(handle)
        self.assertTrue(self.session.cpu_access(unrelated, write=True))
        self.session.acknowledge(fence, 'complete')
        self.assertEqual(self.session.status(fence), 'complete')
        self.assertTrue(self.session.cpu_access(alias))
        self.session.free(self.color)
        with self.assertRaises(ValueError): self.session.cpu_access(self.color)

    def test_timeout_is_not_completion(self):
        fence = self.submit()
        self.session.timeout(fence)
        self.session.timeout(fence)
        self.assertEqual(self.session.status(fence), 'uncertain')
        with self.assertRaises(RuntimeError): self.session.cpu_access(self.color)
        with self.assertRaises(RuntimeError): self.submit()
        self.session.acknowledge(fence, 'cancelled')
        self.assertEqual(self.session.status(fence), 'cancelled')
        self.assertTrue(self.session.cpu_access(self.color, write=True))
        self.submit()

    def test_failure_acknowledgement_recovers_ownership(self):
        fence = self.submit()
        self.session.acknowledge(fence, 'failed')
        self.assertEqual(self.session.status(fence), 'failed')
        self.assertTrue(self.session.cpu_access(self.depth))
        for action in (lambda: self.session.timeout(fence),
                       lambda: self.session.acknowledge(fence, 'complete')):
            with self.assertRaises(RuntimeError): action()
        self.submit()

    def test_submit_rejection_is_atomic(self):
        alias = self.session.register(64, 128)
        cases = [(self.depth, 8, 9, 16), (self.depth, 8, 8, 15),
                 (self.depth, 8, 8, 17), (self.depth, True, 8, 16),
                 (self.depth, 8, 0, 16), (self.depth, MAX_RANGE, 8, 16),
                 (self.depth, 8, MAX_RANGE, 16), (alias, 8, 8, 16)]
        for depth, width, height, stride in cases:
            with self.subTest(width=width, height=height, stride=stride, depth=depth):
                before = (dict(self.session._buffers), dict(self.session._fences), self.session._serial)
                with self.assertRaises(ValueError):
                    self.session.submit(self.color, depth, width=width, height=height, stride=stride)
                self.assertEqual(before, (self.session._buffers, self.session._fences, self.session._serial))
                self.assertIsNone(self.session.active)
        self.submit()

    def test_exact_last_row_range_and_padding(self):
        session = Session(40)
        # Two 6byte rows with 8byte stride need 14bytes, no final padding access.
        color = session.register(0, 14)
        depth = session.register(16, 14)
        fence = session.submit(color, depth, width=3, height=2, stride=8)
        self.assertEqual(session.status(fence), 'pending')

    def test_reset_invalidates_handles_and_fences(self):
        fence = self.submit()
        self.session.timeout(fence)
        self.session.reset_acknowledged()
        replacement = self.session.register(0, 128)
        for old in (self.color, self.depth):
            with self.assertRaises(ValueError): self.session.cpu_access(old)
        with self.assertRaises(ValueError): self.session.status(fence)
        self.assertTrue(self.session.cpu_access(replacement))

    def test_foreign_forged_freed_handles(self):
        foreign = Session(4096).register(0, 128)
        forged = Buffer(self.color.number, self.color.offset, self.color.size)
        self.session.free(self.depth)
        for bad in (foreign, forged, self.depth, None, 1):
            with self.assertRaises(ValueError):
                self.session.submit(self.color, bad, width=8, height=8, stride=16)
            self.assertTrue(self.session.cpu_access(self.color))
        fence = Session(4096)
        other = fence.submit(fence.register(0, 128), fence.register(128, 128), width=8, height=8, stride=16)
        for bad in (other, Fence(other.number), None):
            with self.assertRaises(ValueError): self.session.status(bad)

    def test_registration_and_acknowledgement_bad_inputs(self):
        for offset, size in ((-1, 1), (1, 2), (0, 0), (4096, 1),
                             (4094, 3), (True, 2), (MAX_RANGE + 1, 2)):
            with self.assertRaises(ValueError): self.session.register(offset, size)
        fence = self.submit()
        with self.assertRaises(ValueError): self.session.acknowledge(fence, 'timeout')
        self.assertEqual(self.session.status(fence), 'pending')
        with self.assertRaises(RuntimeError): self.session.cpu_access(self.color)


if __name__ == '__main__':
    unittest.main()
