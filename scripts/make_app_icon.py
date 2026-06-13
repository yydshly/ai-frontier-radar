"""Generate assets/app.ico - a radar-themed Windows icon, with NO third-party deps.

Why this exists: .bat files always show the generic Windows shell icon and cannot
embed their own. The friendly fix is a Desktop/folder *shortcut* (.lnk) that points
at start_app.bat and carries a custom icon (see scripts/create_shortcuts.ps1). This
script renders that icon (a dark tile with concentric radar rings, a sweep wedge and
a blip) directly to a multi-size PNG-embedded .ico using only the stdlib (zlib + struct).

Run:  python scripts/make_app_icon.py
Out:  assets/app.ico  (sizes 256/48/32/16)
"""
from __future__ import annotations

import math
import struct
import zlib
import binascii
from pathlib import Path

# Palette (RGBA).
BG_TOP = (14, 23, 38)       # deep navy
BG_BOT = (8, 14, 24)        # darker navy (vertical gradient)
RING = (52, 211, 153)       # emerald
SWEEP = (52, 211, 153)      # emerald (faded by alpha)
BLIP = (167, 243, 208)      # light mint
GRID = (52, 211, 153)       # faint cross


def _lerp(a, b, t):
    return a + (b - a) * t


def _mix(base, over, alpha):
    """Alpha-composite `over` (rgb) onto `base` (rgb) with `alpha` in [0,1]."""
    return tuple(int(round(_lerp(base[i], over[i], alpha))) for i in range(3))


def _coverage(value, edge, soft):
    """Smooth 0..1 coverage: 1 well inside `edge`, 0 well outside, ramped over `soft`."""
    if soft <= 0:
        return 1.0 if value <= edge else 0.0
    t = (edge - value) / soft + 0.5
    return max(0.0, min(1.0, t))


def render_rgba(size: int) -> bytes:
    """Render the icon at `size`x`size`, supersampled 2x then box-averaged."""
    ss = 2
    big = size * ss
    half = big / 2.0
    pad = big * 0.06
    radius = half - pad          # outer radar radius
    corner = big * 0.22          # rounded-tile corner radius
    soft = ss * 1.2              # AA width in supersampled px

    # Sweep wedge: a faded arc sweeping from `sweep_dir`.
    sweep_dir = math.radians(-35)
    sweep_span = math.radians(70)
    blip_ang = math.radians(-20)
    blip_r = radius * 0.46

    buf = bytearray(big * big * 4)
    for y in range(big):
        for x in range(big):
            dx = x - half
            dy = y - half
            # --- rounded-tile background mask ---
            qx = abs(dx) - (half - pad - corner)
            qy = abs(dy) - (half - pad - corner)
            outside = math.hypot(max(qx, 0.0), max(qy, 0.0)) - corner
            tile = _coverage(outside, 0.0, soft)
            if tile <= 0.0:
                continue  # fully transparent

            # vertical gradient background
            t = y / big
            rgb = tuple(int(round(_lerp(BG_TOP[i], BG_BOT[i], t))) for i in range(3))

            dist = math.hypot(dx, dy)
            ang = math.atan2(dy, dx)

            # --- sweep wedge (under the rings) ---
            da = (ang - sweep_dir) % (2 * math.pi)
            if da <= sweep_span and dist <= radius:
                # brightest at the leading edge (da=0), fading back
                a = (1.0 - da / sweep_span) * 0.33 * _coverage(dist, radius, soft)
                rgb = _mix(rgb, SWEEP, a)

            # --- concentric rings ---
            for rr in (0.40, 0.66, 0.92, 1.0):
                ring_r = radius * rr
                d = abs(dist - ring_r)
                lw = ss * (1.6 if rr == 1.0 else 1.1)
                a = _coverage(d, lw, soft) * (0.95 if rr == 1.0 else 0.55)
                if a > 0:
                    rgb = _mix(rgb, RING, a)

            # --- faint cross grid ---
            if dist <= radius:
                cross = min(abs(dx), abs(dy))
                a = _coverage(cross, ss * 0.6, soft) * 0.18
                if a > 0:
                    rgb = _mix(rgb, GRID, a)

            # --- sweep leading line ---
            line_d = abs((ang - sweep_dir + math.pi) % (2 * math.pi) - math.pi) * dist
            if dist <= radius:
                a = _coverage(line_d, ss * 1.0, soft) * 0.5
                if a > 0:
                    rgb = _mix(rgb, SWEEP, a)

            # --- blip ---
            bx = math.cos(blip_ang) * blip_r
            by = math.sin(blip_ang) * blip_r
            bd = math.hypot(dx - bx, dy - by)
            a = _coverage(bd, ss * 2.4, soft)
            if a > 0:
                rgb = _mix(rgb, BLIP, a)

            i = (y * big + x) * 4
            buf[i] = rgb[0]
            buf[i + 1] = rgb[1]
            buf[i + 2] = rgb[2]
            buf[i + 3] = int(round(255 * tile))

    # Box-average downscale ss->1.
    out = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            r = g = b = a = 0
            for sy in range(ss):
                for sx in range(ss):
                    i = ((y * ss + sy) * big + (x * ss + sx)) * 4
                    r += buf[i]; g += buf[i + 1]; b += buf[i + 2]; a += buf[i + 3]
            n = ss * ss
            o = (y * size + x) * 4
            out[o] = r // n; out[o + 1] = g // n; out[o + 2] = b // n; out[o + 3] = a // n
    return bytes(out)


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", binascii.crc32(tag + data) & 0xFFFFFFFF))


def encode_png(rgba: bytes, size: int) -> bytes:
    raw = bytearray()
    stride = size * 4
    for y in range(size):
        raw.append(0)  # filter type 0 (None)
        raw.extend(rgba[y * stride:(y + 1) * stride])
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return (b"\x89PNG\r\n\x1a\n"
            + _png_chunk(b"IHDR", ihdr)
            + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + _png_chunk(b"IEND", b""))


def build_ico(sizes=(256, 48, 32, 16)) -> bytes:
    pngs = [(s, encode_png(render_rgba(s), s)) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(pngs))  # reserved, type=icon, count
    offset = 6 + 16 * len(pngs)
    entries = bytearray()
    blob = bytearray()
    for s, png in pngs:
        wb = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", wb, wb, 0, 0, 1, 32, len(png), offset)
        blob += png
        offset += len(png)
    return header + bytes(entries) + bytes(blob)


def main():
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "assets"
    out_dir.mkdir(exist_ok=True)
    ico = build_ico()
    out = out_dir / "app.ico"
    out.write_bytes(ico)
    print(f"Wrote {out} ({len(ico)} bytes, sizes 256/48/32/16)")


if __name__ == "__main__":
    main()
