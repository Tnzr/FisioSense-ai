#!/usr/bin/env python3
"""Generate the Asculto PWA app icons (pure stdlib PNG writer).

Renders a white heart on the teal brand background at the requested sizes:
  192 (standard), 512 (standard), 512-maskable (full-bleed, safe zone).

Usage:  python3 scripts/make-icons.py
"""
from __future__ import annotations

import os
import struct
import zlib


def _png(path: str, size: int, draw) -> None:
    """draw(x01, y01) -> (r, g, b, a) for normalized coords, y up."""
    raw = bytearray()
    for j in range(size):
        raw.append(0)  # filter: none
        for i in range(size):
            # 2x2 supersample for a softer edge
            acc = [0, 0, 0, 0]
            for dy in (0, 1):
                for dx in (0, 1):
                    x01 = (i + (dx + 0.5) / 2) / size
                    y01 = 1.0 - (j + (dy + 0.5) / 2) / size
                    px = draw(x01, y01)
                    for k in range(4):
                        acc[k] += px[k]
            r, g, b, a = (round(v / 4) for v in acc)
            raw += bytes((r, g, b, a))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes(raw), 9)
    def chunk(tag: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", ihdr))
        f.write(chunk(b"IDAT", idat))
        f.write(chunk(b"IEND", b""))


def heart_fill(x01: float, y01: float, maskable: bool) -> tuple:
    bg = (0x4C, 0xC2, 0xC4, 255)          # brand teal
    dark = (0x0F, 0x17, 0x20, 255)        # heart contrast ring
    cx, cy, r = 0.5, 0.5, 0.42
    if not maskable and (x01 - cx) ** 2 + (y01 - cy) ** 2 > r ** 2:
        return dark
    # classic heart curve, centered on 0.5,0.5
    hx = (x01 - 0.5) * 2.4
    hy = (y01 - 0.5) * 2.4
    f = (hx * hx + hy * hy - 1) ** 3 - hx * hx * (hy ** 3)
    inside = f <= 0
    edge = 0.0 if inside else min(1.0, max(0.0, (f - 0.0) * 8.0))
    heart = (255, 255, 255, 255)
    if inside:
        return heart
    # soft white edge then dark
    t = min(1.0, edge)
    col = tuple(round(a * (1 - t) + b * t) for a, b in zip(heart, dark))
    return col + (255,)


def main() -> None:
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public", "icons")
    os.makedirs(out, exist_ok=True)
    for name, size, maskable in (
        ("icon-192.png", 192, False),
        ("icon-512.png", 512, False),
        ("icon-512-maskable.png", 512, True),
    ):
        path = os.path.join(out, name)
        _png(path, size, lambda x, y, m=maskable: heart_fill(x, y, m))
        print(f"[icons] {path} ({os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    main()
