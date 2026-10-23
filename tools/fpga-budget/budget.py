# SPDX-License-Identifier: GPL-2.0-only
"""Host-only GPU DDR allocation and readback budget; never accesses devices."""
from dataclasses import asdict, dataclass
from fractions import Fraction
import argparse
import json

ALIGNMENT = 64  # Host study choice, not an established hardware requirement.


def uint(name, value, *, positive=False):
    if type(value) is not int or value < int(positive) or value > (1 << 64) - 1:
        raise ValueError(f"{name} must be a {'positive' if positive else 'nonnegative'} integer within uint64")
    return value


def align(value, alignment=ALIGNMENT):
    return (value + alignment - 1) // alignment * alignment


@dataclass(frozen=True)
class Region:
    name: str
    offset: int
    size: int
    stride: int | None = None


def plan(*, width=640, height=360, capacity_bytes=128 * 1024 * 1024,
         reserved_bytes=1024 * 1024, color_buffers=2, depth=True,
         texture_bytes=0, fps=30, stride_bytes=None, readback="packed",
         available_readback_bps=None):
    """Offsets are relative to a hypothetical DDR arena, not physical addresses.

    RGB565 and uint16 depth use two bytes/pixel. One completed color buffer is
    read per frame. Packed row output omits stride padding; strided includes it.
    Available bandwidth, if supplied, is a caller-provided *payload* rate.
    """
    for name, value in (("width", width), ("height", height),
                        ("capacity_bytes", capacity_bytes), ("color_buffers", color_buffers),
                        ("fps", fps)):
        uint(name, value, positive=True)
    uint("reserved_bytes", reserved_bytes)
    uint("texture_bytes", texture_bytes)
    if type(depth) is not bool:
        raise ValueError("depth must be a boolean")
    if readback not in ("packed", "strided"):
        raise ValueError("readback must be packed or strided")
    row_bytes = width * 2
    if stride_bytes is None:
        stride_bytes = align(row_bytes)
    uint("stride_bytes", stride_bytes, positive=True)
    if stride_bytes < row_bytes or stride_bytes % 2:
        raise ValueError("stride must cover the row and be aligned to two bytes")
    if available_readback_bps is not None:
        uint("available_readback_bps", available_readback_bps, positive=True)
    # Bound generated structures even for an adversarial CLI request.
    if color_buffers > 16:
        raise ValueError("study tool supports at most 16 color buffers")
    cursor = reserved_bytes
    regions = []
    frame_allocation = stride_bytes * height
    for name, size, stride in (
        [(f"color-{i}", frame_allocation, stride_bytes) for i in range(color_buffers)]
        + ([("depth", frame_allocation, stride_bytes)] if depth else [])
        + ([("textures", texture_bytes, None)] if texture_bytes else [])
    ):
        start = align(cursor)
        if start > capacity_bytes or size > capacity_bytes - start:
            raise ValueError(f"{name} exceeds the configured DDR arena")
        regions.append(Region(name, start, size, stride))
        cursor = start + size
    if reserved_bytes > capacity_bytes:
        raise ValueError("reserved bytes exceed capacity")
    used = cursor
    useful_bytes = row_bytes * height
    bytes_per_frame = useful_bytes if readback == "packed" else frame_allocation
    payload_rate = bytes_per_frame * fps
    result = {
        "kind": "analytical_budget", "physical_link_tested": False,
        "linux_runtime_tested": False, "meos_runtime_tested": False,
        "capacity_is_hypothetical": True,
        "format": "RGB565_LE", "depth_format": "uint16" if depth else None,
        "width": width, "height": height, "stride_bytes": stride_bytes,
        "region_alignment_bytes": ALIGNMENT, "capacity_bytes": capacity_bytes,
        "reserved_bytes": reserved_bytes,
        "regions": [asdict(r) for r in regions],
        "region_payload_bytes": sum(r.size for r in regions),
        "padding_bytes": used - reserved_bytes - sum(r.size for r in regions),
        "used_including_reserved_bytes": used, "unallocated_bytes": capacity_bytes - used,
        "readback_mode": readback, "color_payload_bytes_per_frame": useful_bytes,
        "readback_bytes_per_frame": bytes_per_frame, "requested_fps": fps,
        "required_payload_bps": payload_rate, "rate_unit": "bytes/second (not bits/second)",
        "excluded": ["wire framing and CRC", "bus direction changes", "queue/wait latency",
                     "CPU copies and cache synchronization", "GPU rendering", "LCD output",
                     "DDR arbitration and memory controller overhead"],
        "note": "Not a benchmark or a fixed FPGA memory map; no GPU/Linux ABI is defined.",
    }
    if available_readback_bps is not None:
        ceiling = Fraction(available_readback_bps, bytes_per_frame)
        result["assumed_available_payload_bps"] = available_readback_bps
        result["readback_only_fps_ceiling"] = float(ceiling)
        result["readback_only_minimum_ms"] = float(Fraction(bytes_per_frame * 1000, available_readback_bps))
        result["payload_budget_sufficient"] = available_readback_bps >= payload_rate
        result["payload_budget_sufficient_is_not_end_to_end_feasibility"] = True
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name, default in (("width", 640), ("height", 360),
                          ("capacity-bytes", 128 * 1024 * 1024),
                          ("reserved-bytes", 1024 * 1024), ("color-buffers", 2),
                          ("texture-bytes", 0), ("fps", 30)):
        p.add_argument("--" + name, type=int, default=default)
    p.add_argument("--stride-bytes", type=int)
    p.add_argument("--no-depth", action="store_true")
    p.add_argument("--readback", choices=("packed", "strided"), default="packed")
    p.add_argument("--available-readback-bps", type=int, help="Assumed useful payload bytes/second, excluding overhead")
    args = vars(p.parse_args())
    args["depth"] = not args.pop("no_depth")
    try:
        result = plan(**args)
    except ValueError as e:
        p.error(str(e))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
