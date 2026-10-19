#!/usr/bin/env python3
"""Generate the macOS app icon with no external dependencies.

Pure-Python rasteriser: a rounded-rect gradient background with a white
"download" glyph, anti-aliased from signed distance fields. Can emit either a
single 1024x1024 PNG or a complete `.icns` (all sizes, written by hand so it
works even where `iconutil` is unavailable).

    python scripts/make_icon.py out.png
    python scripts/make_icon.py --icns AppIcon.icns
"""

from __future__ import annotations

import math
import struct
import sys
import zlib

SIZE = 1024
RADIUS = 229.0
STROKE = 74.0
HALF = STROKE / 2.0

TOP = (124, 92, 255)      # #7C5CFF
BOTTOM = (59, 43, 214)    # #3B2BD6

# Glyph geometry in the 1024x1024 coordinate space.
SEGMENTS = [
    (512, 214, 512, 560),   # arrow shaft
    (512, 560, 360, 406),   # arrow head (left)
    (512, 560, 664, 406),   # arrow head (right)
    (296, 692, 296, 754),   # tray left
    (296, 754, 728, 754),   # tray bottom
    (728, 754, 728, 692),   # tray right
]

# icns type codes for the standard square sizes macOS reads.
ICNS_TYPES = {
    16: b"icp4", 32: b"icp5", 64: b"icp6", 128: b"ic07",
    256: b"ic08", 512: b"ic09", 1024: b"ic10",
}


def _clamp01(v: float) -> float:
    return 0.0 if v < 0 else (1.0 if v > 1 else v)


def _seg_dist(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    apx, apy = px - ax, py - ay
    abx, aby = bx - ax, by - ay
    denom = abx * abx + aby * aby
    t = 0.0 if denom == 0 else (apx * abx + apy * aby) / denom
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    return math.hypot(apx - abx * t, apy - aby * t)


def _round_rect_cov(x: float, y: float) -> float:
    half = SIZE / 2.0
    qx = abs(x - half) - (half - RADIUS)
    qy = abs(y - half) - (half - RADIUS)
    ax, ay = max(qx, 0.0), max(qy, 0.0)
    d = math.hypot(ax, ay) + min(max(qx, qy), 0.0) - RADIUS
    return _clamp01(0.5 - d)


def _glyph_cov(x: float, y: float) -> float:
    d = min(_seg_dist(x, y, *s) for s in SEGMENTS) - HALF
    return _clamp01(0.5 - d)


def render_rgba() -> bytearray:
    """Render the master 1024x1024 icon as raw RGBA bytes."""
    buf = bytearray(SIZE * SIZE * 4)
    idx = 0
    for py in range(SIZE):
        y = py + 0.5
        t = y / SIZE
        br = TOP[0] + (BOTTOM[0] - TOP[0]) * t
        bg = TOP[1] + (BOTTOM[1] - TOP[1]) * t
        bb = TOP[2] + (BOTTOM[2] - TOP[2]) * t
        for px in range(SIZE):
            x = px + 0.5
            a_bg = _round_rect_cov(x, y)
            a_gl = _glyph_cov(x, y) * a_bg
            buf[idx] = int(br * (1 - a_gl) + 255 * a_gl + 0.5)
            buf[idx + 1] = int(bg * (1 - a_gl) + 255 * a_gl + 0.5)
            buf[idx + 2] = int(bb * (1 - a_gl) + 255 * a_gl + 0.5)
            buf[idx + 3] = int(a_bg * 255 + 0.5)
            idx += 4
    return buf


def downscale(master: bytearray, size: int) -> bytearray:
    """Box-filter from the 1024 master to `size` (1024 must divide evenly)."""
    factor = SIZE // size
    n = factor * factor
    out = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            r = g = b = a = 0
            for dy in range(factor):
                base = ((y * factor + dy) * SIZE + x * factor) * 4
                for dx in range(factor):
                    o = base + dx * 4
                    r += master[o]
                    g += master[o + 1]
                    b += master[o + 2]
                    a += master[o + 3]
            o2 = (y * size + x) * 4
            out[o2] = r // n
            out[o2 + 1] = g // n
            out[o2 + 2] = b // n
            out[o2 + 3] = a // n
    return out


def _png(size: int, pixels: bytes) -> bytes:
    raw = bytearray()
    stride = size * 4
    for row in range(size):
        raw.append(0)  # filter type: none
        raw += pixels[row * stride:(row + 1) * stride]
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + _chunk(b"IEND", b""))


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def write_icns(path: str) -> None:
    master = render_rgba()
    body = b""
    for size, code in ICNS_TYPES.items():
        pixels = master if size == SIZE else downscale(master, size)
        png = _png(size, bytes(pixels))
        body += code + struct.pack(">I", len(png) + 8) + png
    with open(path, "wb") as fh:
        fh.write(b"icns" + struct.pack(">I", 8 + len(body)) + body)


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--icns":
        out = args[1] if len(args) > 1 else "AppIcon.icns"
        write_icns(out)
        print(f"wrote {out} (icns, {len(ICNS_TYPES)} sizes)")
        return 0
    out = args[0] if args else "AppIcon.png"
    with open(out, "wb") as fh:
        fh.write(_png(SIZE, bytes(render_rgba())))
    print(f"wrote {out} ({SIZE}x{SIZE} png)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
