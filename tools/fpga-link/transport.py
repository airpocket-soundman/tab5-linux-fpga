# SPDX-License-Identifier: GPL-2.0-only
"""Bounded byte-stream abstraction. Only the mock backend is implemented."""
from abc import ABC, abstractmethod
import math
import time

from codec import FRAME_SIZE, make_request, mock_reply, validate_response


class Transport(ABC):
    """One in-flight transaction; implementations must respect the deadline.

    Return positive short counts/chunks for partial progress. EOF is b''.
    Raise TimeoutError on deadline expiry; no implicit retry is allowed.
    """
    @abstractmethod
    def write(self, data, deadline):
        raise NotImplementedError

    @abstractmethod
    def read(self, count, deadline):
        raise NotImplementedError

    @abstractmethod
    def reset(self):
        """Discard partial request/response after any transaction failure."""
        raise NotImplementedError


class MockTransport(Transport):
    """One eight-byte endpoint. Fragmentation models short stream transfers."""
    def __init__(self, fragment_size=8):
        if type(fragment_size) is not int or not 1 <= fragment_size <= FRAME_SIZE:
            raise ValueError("fragment size must be in 1..8")
        self.fragment_size = fragment_size
        self.reset()

    def reset(self):
        self.pending = bytearray()
        self.response = bytearray()

    @staticmethod
    def check_deadline(deadline):
        if time.monotonic() >= deadline:
            raise TimeoutError("mock deadline expired")

    def write(self, data, deadline):
        self.check_deadline(deadline)
        if self.response:
            raise RuntimeError("previous mock response has not been consumed")
        if not data or len(self.pending) + len(data) > FRAME_SIZE:
            raise ValueError("invalid or oversized mock request")
        count = min(len(data), self.fragment_size)
        self.pending.extend(data[:count])
        if len(self.pending) == FRAME_SIZE:
            self.response.extend(mock_reply(bytes(self.pending)))
            self.pending.clear()
        return count

    def read(self, count, deadline):
        self.check_deadline(deadline)
        if not self.response:
            raise TimeoutError("no complete mock response available")
        count = min(count, self.fragment_size, len(self.response))
        result = bytes(self.response[:count])
        del self.response[:count]
        return result


class LinkClient:
    def __init__(self, transport, timeout=0.1):
        if not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError("timeout must be finite and in (0, 60] seconds")
        self.transport = transport
        self.timeout = timeout
        self.sequence = 0

    def transfer(self, opcode, first=0, second=0):
        request = make_request(opcode, self.sequence, first, second)
        self.sequence = (self.sequence + 1) & 0xff
        deadline = time.monotonic() + self.timeout
        try:
            sent = 0
            while sent < FRAME_SIZE:
                self._check_deadline(deadline)
                count = self.transport.write(request[sent:], deadline)
                if type(count) is not int or not 0 < count <= FRAME_SIZE - sent:
                    raise OSError("invalid transport write count")
                sent += count
            response = bytearray()
            while len(response) < FRAME_SIZE:
                self._check_deadline(deadline)
                chunk = self.transport.read(FRAME_SIZE - len(response), deadline)
                if not chunk:
                    raise EOFError("transport ended during a response")
                if len(chunk) > FRAME_SIZE - len(response):
                    raise OSError("oversized transport response")
                response.extend(chunk)
            self._check_deadline(deadline)
            if not validate_response(response, request):
                raise ValueError("invalid response CRC, sequence, status or payload")
            return {"request": request.hex(), "response": bytes(response).hex(),
                    "result": list(response[4:6])}
        except Exception:
            self.transport.reset()
            raise

    @staticmethod
    def _check_deadline(deadline):
        if time.monotonic() >= deadline:
            raise TimeoutError("transaction deadline expired")
