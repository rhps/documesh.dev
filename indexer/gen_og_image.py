#!/usr/bin/env python3
"""Generate a simple OG image (1200x630 PNG) with Documesh branding."""
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "app" / "og-image.png"
W, H = 1200, 630

BG = (255, 255, 255)
ACCENT = (75, 83, 32)
SAGE = (146, 154, 104)
LIGHT = (169, 175, 139)
GRID = (240, 244, 248)


def make_png():
    raw = b""
    for y in range(H):
        raw += b"\x00"
        for x in range(W):
            r, g, b = BG
            if y > H - 60:
                r, g, b = ACCENT
            if y < 60 and x < 400:
                r, g, b = LIGHT
            if x % 120 == 0 or y % 120 == 0:
                r, g, b = GRID
            raw += bytes([r, g, b])

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)

    def chunk(ctype, data):
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


OUT.write_bytes(make_png())
print(f"✅ og-image.png ({OUT.stat().st_size / 1024:.0f} KB)")
