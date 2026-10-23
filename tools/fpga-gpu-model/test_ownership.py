# SPDX-License-Identifier: GPL-2.0-only
import unittest
import gc
import weakref
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
                before = (dict(self.session._buffers), dict(self.session._fences), self.session._serial,
                          dict(self.session._versions))
                with self.assertRaises(ValueError):
                    self.session.submit(self.color, depth, width=width, height=height, stride=stride)
                self.assertEqual(before, (self.session._buffers, self.session._fences, self.session._serial,
                                         self.session._versions))
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

    def test_readback_requires_current_successful_image(self):
        fence = self.submit()
        for operation in (lambda: self.session.authorize_readback(fence),
                          lambda: self.session.retire(fence)):
            with self.assertRaises(RuntimeError): operation()
        self.session.timeout(fence)
        with self.assertRaises(RuntimeError): self.session.authorize_readback(fence)
        with self.assertRaises(RuntimeError): self.session.retire(fence)
        self.session.acknowledge(fence, 'complete')
        self.assertIs(self.session.authorize_readback(fence), self.color)
        # CPU reads preserve contents; write authorization conservatively invalidates.
        self.session.cpu_access(self.color)
        self.assertIs(self.session.authorize_readback(fence), self.color)
        alias = self.session.register(2, 16)
        self.session.cpu_access(alias, write=True)
        with self.assertRaises(RuntimeError): self.session.authorize_readback(fence)

    def test_old_completed_fence_cannot_read_new_submission(self):
        old = self.submit()
        self.session.acknowledge(old, 'complete')
        current = self.submit()
        with self.assertRaises(RuntimeError): self.session.authorize_readback(old)
        self.session.acknowledge(current, 'complete')
        with self.assertRaises(RuntimeError): self.session.authorize_readback(old)
        self.assertIs(self.session.authorize_readback(current), self.color)

    def test_submission_through_alias_supersedes_old_image(self):
        old = self.submit()
        self.session.acknowledge(old, 'complete')
        alias = self.session.register(0, 128)
        new = self.session.submit(alias, self.depth, width=8, height=8, stride=16)
        self.session.acknowledge(new, 'failed')
        with self.assertRaises(RuntimeError): self.session.authorize_readback(old)
        with self.assertRaises(RuntimeError): self.session.authorize_readback(new)

    def test_failed_cancelled_retired_reset_and_freed_readback(self):
        for outcome in ('failed', 'cancelled'):
            fence = self.submit()
            self.session.acknowledge(fence, outcome)
            with self.assertRaises(RuntimeError): self.session.authorize_readback(fence)
            self.session.retire(fence)
            with self.assertRaises(ValueError): self.session.authorize_readback(fence)
        fence = self.submit()
        self.session.acknowledge(fence, 'complete')
        self.session.free(self.color)
        with self.assertRaises(ValueError): self.session.authorize_readback(fence)
        self.session.reset_acknowledged()
        with self.assertRaises(ValueError): self.session.authorize_readback(fence)

    def test_retirement_releases_buffer_references_and_bounds_metadata(self):
        session = Session(512)
        color, depth = session.register(0, 128), session.register(128, 128)
        color_ref, depth_ref = weakref.ref(color), weakref.ref(depth)
        fence = session.submit(color, depth, width=8, height=8, stride=16)
        session.acknowledge(fence, 'complete')
        session.free(color)
        session.free(depth)
        del color, depth
        gc.collect()
        self.assertIsNotNone(color_ref())  # Retained by unretired fence metadata.
        session.retire(fence)
        gc.collect()
        self.assertIsNone(color_ref())
        self.assertIsNone(depth_ref())
        self.assertEqual(session._fences, {})
        with self.assertRaises(ValueError): session.retire(fence)
        for _ in range(100):
            fence = self.submit()
            self.session.acknowledge(fence, 'complete')
            self.session.retire(fence)
        self.assertEqual(len(self.session._fences), 0)


if __name__ == '__main__':
    unittest.main()
