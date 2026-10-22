# SPDX-License-Identifier: GPL-2.0-only
import hashlib
import json
from pathlib import Path
import random
import time
import unittest

from codec import (ID, ECHO, INVERT, crc16, make_request, mock_reply, seal,
                   validate_response)
from fpga_link import check_vectors
from transport import LinkClient, MockTransport


class BrokenTransport(MockTransport):
    def __init__(self, fault):
        self.fault = fault
        self.was_reset = False
        super().__init__(fragment_size=1)

    def reset(self):
        self.was_reset = True
        super().reset()

    def read(self, count, deadline):
        if self.fault == "timeout":
            raise TimeoutError("injected timeout")
        if self.fault == "eof":
            return b""
        if self.fault == "oversize":
            return b"x" * 9
        result = super().read(count, deadline)
        return bytes(v ^ 1 for v in result) if self.fault == "corrupt" else result


class LinkTests(unittest.TestCase):
    def test_source_hashes(self):
        root = Path(__file__).parent
        manifest = json.loads((root / "SOURCE.json").read_text())
        for entry in manifest["files"]:
            self.assertEqual(hashlib.sha256((root / entry["local_path"]).read_bytes()).hexdigest(),
                             entry["sha256"])

    def test_all_golden_vectors(self):
        self.assertEqual(check_vectors(), 583)

    def test_crc_known_answer_and_independent_bitwise(self):
        self.assertEqual(crc16(b"123456789"), 0x29b1)
        self.assertEqual(crc16(b""), 0xffff)
        rng = random.Random(20261022)
        for size in (0, 1, 6, 8, 31, 256, 4096):
            data = bytes(rng.randrange(256) for _ in range(size))
            expected = 0xffff
            for value in data:
                expected ^= value << 8
                for _ in range(8):
                    expected = ((expected << 1) ^ (0x1021 if expected & 0x8000 else 0)) & 0xffff
            self.assertEqual(crc16(data), expected)

    def test_all_values_and_sequence_wrap(self):
        client = LinkClient(MockTransport())
        for value in range(256):
            for opcode in (ECHO, INVERT):
                result = client.transfer(opcode, value, value ^ 0xa5)
                self.assertEqual(result["result"],
                                 [value, value ^ 0xa5] if opcode == ECHO
                                 else [value ^ 255, value ^ 0xa5 ^ 255])
        self.assertEqual(client.sequence, 0)

    def test_fragmented_stream(self):
        for size in range(1, 9):
            client = LinkClient(MockTransport(size))
            self.assertEqual(client.transfer(ID)["result"], [84, 80])
            self.assertEqual(client.transfer(ECHO, 0x1a, 0x0a)["result"], [0x1a, 0x0a])

    def test_all_response_bits_and_resealed_fields(self):
        request = make_request(INVERT, 255, 0x55, 0xaa)
        response = mock_reply(request)
        for bit in range(64):
            changed = bytearray(response)
            changed[bit // 8] ^= 1 << (bit % 8)
            self.assertFalse(validate_response(changed, request))
        for index in range(6):
            prefix = bytearray(response[:6])
            prefix[index] ^= 1
            self.assertFalse(validate_response(seal(prefix), request))

    def test_short_and_long_frames(self):
        request = make_request(ID, 0)
        for size in (0, 1, 7, 9, 4096):
            self.assertFalse(validate_response(bytes(size), request))
            with self.assertRaises(ValueError):
                mock_reply(bytes(size))

    def test_uint8_input_validation(self):
        for bad in (-1, 256, True, 1.0, "2"):
            for index in range(4):
                args = [ECHO, 0, 0, 0]
                args[index] = bad
                with self.assertRaises(ValueError):
                    make_request(*args)

    def test_invalid_payload_prefix(self):
        for size in (0, 5, 7):
            with self.assertRaises(ValueError):
                seal(bytes(size))

    def test_unknown_opcode_rejected(self):
        for opcode in range(256):
            if opcode not in (ID, ECHO, INVERT):
                request = make_request(opcode, 0)
                response = mock_reply(request)
                self.assertEqual(response[1], 2)
                self.assertFalse(validate_response(response, request))

    def test_failure_discards_partial_state_and_next_request_recovers(self):
        for fault, error in (("timeout", TimeoutError), ("eof", EOFError),
                             ("oversize", OSError), ("corrupt", ValueError)):
            transport = BrokenTransport(fault)
            transport.was_reset = False
            client = LinkClient(transport)
            with self.assertRaises(error):
                client.transfer(ID)
            self.assertTrue(transport.was_reset)
            self.assertFalse(transport.pending or transport.response)
            transport.fault = None
            self.assertEqual(client.transfer(ID)["result"], [84, 80])

    def test_pending_response_blocks_next_request(self):
        transport = MockTransport()
        transport.write(make_request(ID, 0), time.monotonic() + 1)
        with self.assertRaises(RuntimeError):
            transport.write(make_request(ID, 1), time.monotonic() + 1)
        transport.reset()
        self.assertEqual(LinkClient(transport).transfer(ID)["result"], [84, 80])

    def test_mock_expired_deadline(self):
        with self.assertRaises(TimeoutError):
            MockTransport().write(make_request(ID, 0), time.monotonic() - 1)

    def test_invalid_configuration(self):
        for size in (0, 9, True, 1.5):
            with self.assertRaises(ValueError):
                MockTransport(size)
        for timeout in (0, -1, float("nan"), float("inf"), 61):
            with self.assertRaises(ValueError):
                LinkClient(MockTransport(), timeout)


if __name__ == "__main__":
    unittest.main()
