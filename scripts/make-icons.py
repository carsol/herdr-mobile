#!/usr/bin/env python3
"""Rasterize the app icon (rounded square + H + status dot) to PNG. Stdlib only."""
import os, struct, sys, zlib

def png(size, path):
    r = size * 112 // 512
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            # rounded-rect mask
            cx = min(max(x, r), size - 1 - r); cy = min(max(y, r), size - 1 - r)
            inside = (x - cx) ** 2 + (y - cy) ** 2 <= r * r
            px = (0x14, 0x18, 0x23, 255) if inside else (0, 0, 0, 0)
            X, Y = x * 512 / size, y * 512 / size
            if inside and ((120 <= X < 184 or 328 <= X < 392) and 128 <= Y < 384 or 184 <= X < 328 and 240 <= Y < 304):
                px = (0x5b, 0x8c, 0xff, 255)
            if inside and (X - 404) ** 2 + (Y - 404) ** 2 <= 36 ** 2:
                px = (0x3e, 0xcf, 0x8e, 255)
            row += bytes(px)
        rows.append(b"\x00" + bytes(row))
    def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    data += chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b"")
    open(path, "wb").write(data)

out = os.path.join(os.path.dirname(__file__), "..", "herdr_mobile", "static")
for s in (180, 512):
    png(s, os.path.join(out, f"icon-{s}.png"))
print("ok")
