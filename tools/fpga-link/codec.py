# SPDX-License-Identifier: GPL-2.0-only
"""Independent Python implementation of the GPU project's bringup-v0 wire format.

See SOURCE.json and vendor/link_protocol.h. This is not the future DDR3 ABI.
"""
import binascii

FRAME_SIZE = 8
ID, ECHO, INVERT = 1, 2, 3


def uint8(value):
    if type(value) is not int or not 0 <= value <= 255:
        raise ValueError("expected an integer in 0..255")
    return value


def crc16(data):
    """CCITT-FALSE: poly 1021, init ffff, no reflection or final XOR."""
    return binascii.crc_hqx(data, 0xffff)


def seal(prefix):
    if len(prefix) != 6:
        raise ValueError("frame prefix must contain exactly six bytes")
    return bytes(prefix) + crc16(prefix).to_bytes(2, "little")


def valid_frame(frame, magic):
    return (len(frame) == FRAME_SIZE and frame[0] == magic and frame[3] == 2
            and int.from_bytes(frame[6:], "little") == crc16(frame[:6]))


def make_request(opcode, sequence, first=0, second=0):
    return seal(bytes((0xa5, uint8(opcode), uint8(sequence), 2,
                       uint8(first), uint8(second))))


def expected_payload(request):
    opcode = request[1]
    if opcode == ID:
        return b"TP"
    if opcode == ECHO:
        return request[4:6]
    if opcode == INVERT:
        return bytes(value ^ 0xff for value in request[4:6])
    raise ValueError("unknown bringup-v0 opcode")


def validate_response(response, request):
    # Deliberately matches the existing C host validator's contract: the
    # caller creates a valid request; response CRC, seq, status and result
    # are checked. A bad request is rejected by the mock endpoint instead.
    if len(request) != FRAME_SIZE or not valid_frame(response, 0x5a):
        return False
    if response[1] != 0 or response[2] != request[2]:
        return False
    try:
        return response[4:6] == expected_payload(request)
    except ValueError:
        return False


def mock_reply(request):
    """Pure byte-level FPGA substitute; no clocks, GPIOs, IRQs or DDR3."""
    if len(request) != FRAME_SIZE:
        raise ValueError("mock requires a complete eight-byte request")
    status, result = 0, b"\x00\x00"
    if not valid_frame(request, 0xa5):
        status = 1
    else:
        try:
            result = expected_payload(request)
        except ValueError:
            status = 2
    return seal(bytes((0x5a, status, request[2], 2)) + result)
