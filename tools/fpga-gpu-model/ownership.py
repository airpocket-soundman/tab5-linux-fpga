# SPDX-License-Identifier: GPL-2.0-only
"""Host-only lifecycle model. No wire ABI, rendering, DMA or device access."""
from dataclasses import dataclass

MAX_RANGE = (1 << 64) - 1  # Model bound, not a frozen hardware address width.


def integer(value, name, positive=False):
    if type(value) is not int or not (int(positive) <= value <= MAX_RANGE):
        raise ValueError(f"invalid {name}")
    return value


@dataclass(frozen=True, eq=False)
class Buffer:
    number: int
    offset: int
    size: int


@dataclass(frozen=True, eq=False)
class Fence:
    number: int


class Session:
    """Single outstanding render job; explicit reset or acknowledgement recovers ownership.

    register() aliases are allowed to model bad application registrations. submit()
    rejects color/depth overlap. No memory storage or pixel operations are provided.
    """
    def __init__(self, capacity):
        self.capacity = integer(capacity, "capacity", True)
        self._serial = 0
        self._buffers = {}
        self._fences = {}
        self._versions = {}
        self.active = None

    def register(self, offset, size):
        integer(offset, "offset")
        integer(size, "size", True)
        if offset % 2 or offset > self.capacity or size > self.capacity - offset:
            raise ValueError("buffer outside arena or unaligned")
        self._serial += 1
        handle = Buffer(self._serial, offset, size)
        self._buffers[handle] = "cpu"
        self._versions[handle] = 0
        return handle

    def _known(self, handle):
        if not isinstance(handle, Buffer) or handle not in self._buffers:
            raise ValueError("foreign, forged, freed or reset buffer")

    def cpu_access(self, handle, *, write=False):
        self._known(handle)
        if type(write) is not bool:
            raise ValueError("write must be boolean")
        # Alias registrations must not bypass device ownership of the same bytes.
        for other, owner in self._buffers.items():
            if owner == "device" and self._overlap(handle, other):
                raise RuntimeError("buffer bytes are device owned")
        if write:
            self._invalidate(handle)
        return True

    def _invalidate(self, handle):
        for other in self._buffers:
            if self._overlap(handle, other):
                self._versions[other] += 1

    def free(self, handle):
        self.cpu_access(handle)
        del self._buffers[handle]
        del self._versions[handle]

    @staticmethod
    def _overlap(a, b):
        return a.offset < b.offset + b.size and b.offset < a.offset + a.size

    def _image(self, handle, width, height, stride):
        self.cpu_access(handle)
        integer(width, "width", True)
        integer(height, "height", True)
        integer(stride, "stride", True)
        # Subtract/divide checks avoid bounded-address arithmetic overflow.
        if width > MAX_RANGE // 2:
            raise ValueError("row byte overflow")
        row = width * 2
        if stride < row or stride % 2:
            raise ValueError("stride must cover RGB565/uint16 row and be two-byte aligned")
        if row > handle.size or height - 1 > (handle.size - row) // stride:
            raise ValueError("image exceeds registered buffer")

    def submit(self, color, depth, *, width, height, stride):
        if self.active is not None:
            raise RuntimeError("one job is already outstanding")
        self._image(color, width, height, stride)
        self._image(depth, width, height, stride)
        if self._overlap(color, depth):
            raise ValueError("color and depth regions overlap")
        # Publish only after every check has succeeded.
        self._serial += 1
        fence = Fence(self._serial)
        self._invalidate(color)
        self._invalidate(depth)
        self._fences[fence] = ("pending", (color, depth), self._versions[color])
        self._buffers[color] = self._buffers[depth] = "device"
        self.active = fence
        return fence

    def status(self, fence):
        if not isinstance(fence, Fence) or fence not in self._fences:
            raise ValueError("foreign, forged or reset fence")
        return self._fences[fence][0]

    def timeout(self, fence):
        state = self.status(fence)
        if state not in ("pending", "uncertain"):
            raise RuntimeError("job is already terminal")
        self._fences[fence] = ("uncertain", *self._fences[fence][1:])

    def acknowledge(self, fence, outcome):
        """A trusted backend has confirmed completion, stopped failure or cancellation.

        failure here means execution has stopped; a local timeout is not such an
        acknowledgement. failed/cancelled image contents remain invalid.
        """
        state = self.status(fence)
        if outcome not in ("complete", "failed", "cancelled"):
            raise ValueError("invalid acknowledgement")
        if state not in ("pending", "uncertain"):
            raise RuntimeError("job is already terminal")
        buffers = self._fences[fence][1]
        self._fences[fence] = (outcome, *self._fences[fence][1:])
        for handle in buffers:
            self._buffers[handle] = "cpu"
        self.active = None

    def authorize_readback(self, fence):
        """Authorize the completed color image only while its contents remain current."""
        if self.status(fence) != "complete":
            raise RuntimeError("readback requires successful completion")
        _, (color, _), generation = self._fences[fence]
        self.cpu_access(color)
        if self._versions[color] != generation:
            raise RuntimeError("completed color contents have been superseded")
        return color

    def retire(self, fence):
        """Release terminal fence metadata and its references to buffer handles."""
        if self.status(fence) not in ("complete", "failed", "cancelled"):
            raise RuntimeError("cannot retire an outstanding job")
        del self._fences[fence]

    def reset_acknowledged(self):
        """Call only after backend reset has actually stopped all device access."""
        self._buffers.clear()
        self._fences.clear()
        self._versions.clear()
        self.active = None
