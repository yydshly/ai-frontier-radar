"""content_video — Pillow-based scene image renderer.

Renders each VideoScene into a 1080x1920 PNG using Pillow.
V1.5 storyboard-first: dedicated renderers per scene_type.
"""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from app.application.content_video.fonts import load_cjk_font

# Default output size (9:16 portrait)
DEFAULT_W = 1080
DEFAULT_H = 1920

# ── Colour palette ───────────────────────────────────────────────────────────────

C_BG = (4, 10, 20)              # #040a14  deep dark blue
C_BG_MID = (8, 18, 34)          # #081222  mid-tone dark
C_PANEL = (15, 23, 42, 230)     # rgba dark panel
C_PANEL_ALT = (10, 18, 30, 235) # rgba alternate panel
C_ACCENT = (52, 211, 153)        # #34d399  bright green
C_ACCENT_2 = (59, 130, 246)     # #3b82f6  blue accent
C_TEXT = (248, 250, 252)         # #f8fafc  near-white
C_TEXT_DIM = (203, 213, 225)    # #cbd5e1  medium gray
C_TEXT_MUTED = (148, 163, 184)  # #94a3b8  muted gray
C_LINE = (255, 255, 255, 24)    # rgba white 9%
C_CARD_BORDER = (52, 211, 153, 90)  # rgba green border

# ── Safe area constants ─────────────────────────────────────────────────────────

TOP_SAFE = 96
BOTTOM_SAFE = 120
SIDE_MARGIN = 72


# ── Font helpers ────────────────────────────────────────────────────────────────

def _font(size: int, bold: bool = False):
    return load_cjk_font(size, bold=bold)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """Character-level wrap for Chinese text."""
    if not text:
        return []
    lines = []
    current = ""
    for ch in text:
        test = current + ch
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines


# ── Primitive drawing helpers ──────────────────────────────────────────────────

def _draw_background(img: Image.Image, w: int, h: int) -> ImageDraw.Image:
    """Draw a subtle gradient background."""
    draw = ImageDraw.Draw(img)
    # Top → bottom gradient (dark top, slightly lighter bottom)
    for y in range(h):
        ratio = y / h
        r = int(C_BG[0] + (C_BG_MID[0] - C_BG[0]) * ratio)
        g = int(C_BG[1] + (C_BG_MID[1] - C_BG[1]) * ratio)
        b = int(C_BG[2] + (C_BG_MID[2] - C_BG[2]) * ratio)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    return draw


def _draw_brand_header(draw: ImageDraw.Image, w: int, date_label: str | None = None) -> int:
    """Draw the top brand bar. Returns y position after header."""
    brand = "◎ AI 前沿雷达"
    brand_font = _font(32, bold=True)
    bbox = draw.textbbox((0, 0), brand, font=brand_font)
    brand_w = bbox[2] - bbox[0]

    # Accent dot + brand text
    dot_x = (w - brand_w) // 2 - 14
    dot_y = TOP_SAFE + 4
    draw.ellipse([dot_x, dot_y, dot_x + 10, dot_y + 10], fill=C_ACCENT)

    draw.text(((w - brand_w) // 2, TOP_SAFE), brand, font=brand_font, fill=C_ACCENT)

    # Thin accent rule below brand
    rule_y = TOP_SAFE + bbox[3] - bbox[1] + 18
    draw.rectangle([(w // 4, rule_y), (w - w // 4, rule_y + 3)], fill=C_ACCENT)

    return rule_y + 16


def _draw_footer(draw: ImageDraw.Image, w: int, h: int, label: str = "AI Frontier Radar") -> None:
    """Draw centered footer."""
    footer_font = _font(16)
    bbox = draw.textbbox((0, 0), label, font=footer_font)
    x = (w - bbox[2]) // 2
    draw.text((x, h - 36), label, font=footer_font, fill=C_TEXT_MUTED)


def _draw_panel(draw: ImageDraw.Image, left: int, top: int, right: int, bottom: int,
                *, fill=C_PANEL, outline=C_CARD_BORDER, radius: int = 20) -> None:
    """Draw a rounded panel with fill and border."""
    draw.rounded_rectangle([left, top, right, bottom], radius=radius, fill=fill)
    draw.rounded_rectangle([left, top, right, bottom], radius=radius, outline=outline, width=1)


def _draw_chip(draw: ImageDraw.Image, text: str, x: int, y: int,
               *, bg=(52, 211, 153, 30), fg=C_ACCENT, font_size: int = 18) -> int:
    """Draw a small chip/badge. Returns chip width."""
    f = _font(font_size, bold=True)
    bbox = draw.textbbox((0, 0), text, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = 10, 5
    draw.rounded_rectangle([x, y, x + tw + pad_x * 2, y + th + pad_y * 2],
                          radius=8, fill=bg)
    draw.text((x + pad_x, y + pad_y), text, font=f, fill=fg)
    return tw + pad_x * 2


def _draw_waveform(draw: ImageDraw.Image, x: int, y: int, width: int, height: int,
                    color=C_ACCENT) -> None:
    """Draw a decorative waveform as a series of vertical bars."""
    import random
    # Use a seeded random for consistent "shape"
    rng = random.Random(42)
    num_bars = 28
    bar_w = width // (num_bars * 2)
    if bar_w < 2:
        bar_w = 2
    gap = bar_w
    for i in range(num_bars):
        bar_h = int(height * (0.3 + rng.random() * 0.7))
        bx = x + i * (bar_w + gap)
        by = y + (height - bar_h) // 2
        draw.rounded_rectangle([bx, by, bx + bar_w - 1, by + bar_h],
                               radius=max(1, bar_w // 2), fill=color)


def _draw_number_badge(draw: ImageDraw.Image, num: int, x: int, y: int) -> None:
    """Draw a large number badge (e.g. 01, 02)."""
    label = f"{num:02d}"
    f = _font(48, bold=True)
    draw.text((x, y), label, font=f, fill=C_ACCENT)


def _centered_text(draw: ImageDraw.Image, text: str, font, y: int, w: int,
                   *, fill=C_TEXT) -> None:
    """Draw centered text at given y."""
    bbox = draw.textbbox((0, 0), text, font=font)
    x = (w - (bbox[2] - bbox[0])) // 2
    draw.text((x, y), text, font=font, fill=fill)


# ── Scene-specific renderers ──────────────────────────────────────────────────

def _render_opening_summary(scene, w: int, h: int) -> Image.Image:
    """Scene 1: Opening summary — brand + date + top-3 signal chips.

    Layout:
      top: brand header
      upper-mid: main title + subtitle
      mid: 3 signal chips in a row
      lower-mid: tagline
      bottom: footer
    """
    img = Image.new("RGBA", (w, h), C_BG)
    draw = _draw_background(img, w, h)

    header_y = _draw_brand_header(draw, w, getattr(scene, 'source_label', None))

    # Main title
    title_font = _font(60, bold=True)
    title_text = "今日 AI 前沿简报"
    bbox = draw.textbbox((0, 0), title_text, font=title_font)
    title_y = header_y + 30
    _centered_text(draw, title_text, title_font, title_y, w)

    # Subtitle / date
    date_text = getattr(scene, 'source_label', None) or "最新前沿情报"
    sub_font = _font(26)
    sub_y = title_y + (bbox[3] - bbox[1]) + 16
    _centered_text(draw, date_text, sub_font, sub_y, w, fill=C_TEXT_DIM)

    # Signal chips row (from visual_lines or hardcoded from metadata)
    chips = []
    for vl in getattr(scene, 'visual_lines', [])[:3]:
        vl = vl.strip()
        if vl:
            chips.append(vl)

    chip_y = sub_y + (bbox[3] - bbox[1]) + 60
    total_chip_width = sum(len(c) * 28 + 40 for c in chips[:3])
    start_x = (w - total_chip_width) // 2

    cx = start_x
    for chip_text in chips[:3]:
        cw = _draw_chip(draw, chip_text, cx, chip_y, font_size=20)
        cx += cw + 20

    # Tagline
    tag_y = chip_y + 60
    tagline_font = _font(22)
    tagline_text = "扫码查看完整报告 · 语音播报 · 全部文章原文"
    _centered_text(draw, tagline_text, tagline_font, tag_y, w, fill=C_TEXT_MUTED)

    _draw_footer(draw, w, h)
    return img


def _render_summary_overview(scene, w: int, h: int) -> Image.Image:
    """Scene 2: Summary overview — numbered list of core judgments.

    Layout:
      top: brand header
      title: 今日最值得关注
      body: numbered items 01 02 03 with left number + right text
      bottom: footer
    """
    img = Image.new("RGBA", (w, h), C_BG)
    draw = _draw_background(img, w, h)
    header_y = _draw_brand_header(draw, w)

    # Page title
    title_font = _font(44, bold=True)
    title_text = getattr(scene, 'visual_title', '') or "今日最值得关注"
    title_y = header_y + 20
    _centered_text(draw, title_text, title_font, title_y, w)

    # Numbered items
    content_top = title_y + (draw.textbbox((0, 0), title_text, font=title_font)[3] - draw.textbbox((0, 0), title_text, font=title_font)[1]) + 40
    content_left = SIDE_MARGIN + 20
    content_right = w - SIDE_MARGIN - 20
    item_h = 120

    lines = getattr(scene, 'visual_lines', [])
    if not lines:
        lines = [getattr(scene, 'visual_title', '')]

    for idx, line in enumerate(lines[:3], start=1):
        iy = content_top + (idx - 1) * item_h
        # Number badge
        _draw_number_badge(draw, idx, content_left, iy)
        # Panel behind text
        panel_left = content_left + 80
        panel_right = content_right
        panel_top = iy - 8
        panel_bottom = iy + 70
        _draw_panel(draw, panel_left, panel_top, panel_right, panel_bottom,
                    fill=C_PANEL_ALT, radius=12)
        # Text
        text_lines = _wrap_text(draw, line.strip(), _font(26), panel_right - panel_left - 30)
        for t_idx, tl in enumerate(text_lines[:2]):
            ty = panel_top + 16 + t_idx * 38
            draw.text((panel_left + 14, ty), tl, font=_font(26), fill=C_TEXT)

    _draw_footer(draw, w, h)
    return img


def _render_signal(scene, w: int, h: int) -> Image.Image:
    """Signal page — one signal per scene with waveform decoration.

    Layout:
      top: SIGNAL badge + source label
      upper-mid: signal title
      mid: explanation lines in a card panel
      lower-mid: waveform decoration
      bottom: footer + page number
    """
    img = Image.new("RGBA", (w, h), C_BG)
    draw = _draw_background(img, w, h)
    _draw_brand_header(draw, w)

    # Top label row
    label_y = TOP_SAFE + 80
    # "SIGNAL" chip
    _draw_chip(draw, "SIGNAL", SIDE_MARGIN, label_y, font_size=18)

    # Signal index (if available from metadata)
    signal_idx = getattr(scene, 'metadata', {}).get('signal_index', None)
    if signal_idx is not None:
        idx_label = f"#{signal_idx + 1}"
        _draw_chip(draw, idx_label, SIDE_MARGIN + 110, label_y, font_size=18,
                   bg=(59, 130, 246, 40), fg=C_ACCENT_2)

    # Source label top-right
    source = getattr(scene, 'source_label', None)
    if source:
        sf = _font(18)
        sbbox = draw.textbbox((0, 0), source, font=sf)
        sx = w - SIDE_MARGIN - (sbbox[2] - sbbox[0])
        draw.text((sx, label_y), source, font=sf, fill=C_TEXT_MUTED)

    # Signal title
    title_y = label_y + 56
    title_text = getattr(scene, 'visual_title', '') or "信号"
    # Try large font first, scale down if needed
    title_font = _font(48, bold=True)
    tbbox = draw.textbbox((0, 0), title_text, font=title_font)
    if tbbox[2] - tbbox[0] > w - 2 * SIDE_MARGIN - 20:
        title_font = _font(36, bold=True)
        tbbox = draw.textbbox((0, 0), title_text, font=title_font)
    _centered_text(draw, title_text, title_font, title_y, w)

    # Card panel with explanation
    card_top = title_y + (tbbox[3] - tbbox[1]) + 30
    card_bottom = h - BOTTOM_SAFE - 100
    card_left = SIDE_MARGIN
    card_right = w - SIDE_MARGIN
    _draw_panel(draw, card_left, card_top, card_right, card_bottom, radius=20)

    # Explanation lines
    body_font = _font(28)
    line_y = card_top + 24
    body_lines = getattr(scene, 'visual_lines', [])
    for line in body_lines[:4]:
        line = line.strip()
        if not line:
            continue
        wrapped = _wrap_text(draw, line, body_font, card_right - card_left - 40)
        for wl in wrapped:
            if line_y + 42 > card_bottom - 10:
                draw.text((card_left + 20, line_y), "…", font=body_font, fill=C_TEXT_DIM)
                line_y += 42
                break
            wl_bbox = draw.textbbox((0, 0), wl, font=body_font)
            lx = (w - (wl_bbox[2] - wl_bbox[0])) // 2
            draw.text((lx, line_y), wl, font=body_font, fill=C_TEXT)
            line_y += 42
        line_y += 8

    # Waveform decoration above footer
    wf_y = h - BOTTOM_SAFE - 40
    wf_x = (w - 300) // 2
    _draw_waveform(draw, wf_x, wf_y, 300, 20)

    _draw_footer(draw, w, h)
    return img


def _render_supporting_notes(scene, w: int, h: int) -> Image.Image:
    """Supporting notes — secondary observations in a compact list format.

    Layout:
      top: brand header
      title: 补充观察
      body: bullet-like cards for each note
      bottom: footer
    """
    img = Image.new("RGBA", (w, h), C_BG)
    draw = _draw_background(img, w, h)
    header_y = _draw_brand_header(draw, w)

    # Title
    title_font = _font(40, bold=True)
    title_text = getattr(scene, 'visual_title', '') or "补充观察"
    title_y = header_y + 20
    _centered_text(draw, title_text, title_font, title_y, w)

    # Items
    content_top = title_y + 60
    content_left = SIDE_MARGIN + 10
    content_right = w - SIDE_MARGIN - 10
    item_h = 100

    lines = getattr(scene, 'visual_lines', [])
    for idx, line in enumerate(lines[:4], start=1):
        iy = content_top + (idx - 1) * item_h
        # Small bullet
        bx = content_left
        by = iy + 8
        draw.ellipse([bx, by, bx + 8, by + 8], fill=C_ACCENT)
        # Text
        text_lines = _wrap_text(draw, line.strip(), _font(26), content_right - content_left - 30)
        for t_idx, tl in enumerate(text_lines[:2]):
            ty = iy + t_idx * 36
            draw.text((bx + 20, ty), tl, font=_font(26), fill=C_TEXT_DIM)

    _draw_footer(draw, w, h)
    return img


def _render_closing_cta(scene, w: int, h: int) -> Image.Image:
    """Closing CTA — QR + call to action.

    Layout:
      top: brand header
      center: title + subtitle
      QR area: centered placeholder or real QR
      bottom: footer
    """
    img = Image.new("RGBA", (w, h), C_BG)
    draw = _draw_background(img, w, h)
    _draw_brand_header(draw, w)

    # Title
    title_font = _font(52, bold=True)
    title_text = "查看完整报告"
    title_y = TOP_SAFE + 140
    _centered_text(draw, title_text, title_font, title_y, w)

    # Subtitle
    sub_font = _font(26)
    sub_text = "扫码查看完整报告 · 语音播报 · 全部原文链接"
    sub_y = title_y + 70
    _centered_text(draw, sub_text, sub_font, sub_y, w, fill=C_TEXT_DIM)

    # QR code area (placeholder rectangle with label)
    qr_left = (w - 200) // 2
    qr_right = qr_left + 200
    qr_top = sub_y + 50
    qr_bottom = qr_top + 200
    # Draw a styled QR placeholder
    _draw_panel(draw, qr_left, qr_top, qr_right, qr_bottom,
                fill=(15, 23, 42, 200), outline=C_CARD_BORDER, radius=16)

    # QR label inside
    qr_label = "[ 扫码区域 ]"
    qr_label_font = _font(20)
    qlbbox = draw.textbbox((0, 0), qr_label, font=qr_label_font)
    qlx = (w - (qlbbox[2] - qlbbox[0])) // 2
    draw.text((qlx, qr_top + 88), qr_label, font=qr_label_font, fill=C_TEXT_MUTED)

    # Hint text
    hint_font = _font(18)
    hint_text = "完整报告包含全文、来源链接和语音播报"
    _centered_text(draw, hint_text, hint_font, qr_bottom + 24, w, fill=C_TEXT_MUTED)

    _draw_footer(draw, w, h)
    return img


# ── Legacy renderers (kept for compatibility) ─────────────────────────────────

def _render_cover(scene, w: int, h: int) -> Image.Image:
    """Legacy cover — delegates to opening_summary."""
    return _render_opening_summary(scene, w, h)


def _render_card(scene, w: int, h: int, title_color=C_ACCENT) -> Image.Image:
    """Legacy card — delegates to signal."""
    return _render_signal(scene, w, h)


# ── Main entry point ───────────────────────────────────────────────────────────

def render_scene_image(scene, output_path: Path, *, size: str = "1080x1920") -> None:
    """Render a VideoScene to a PNG file.

    Dispatch to the appropriate scene-type renderer.
    """
    try:
        w_str, h_str = size.split("x")
        w, h = int(w_str), int(h_str)
    except (ValueError, AttributeError):
        w, h = DEFAULT_W, DEFAULT_H

    scene_type = getattr(scene, 'scene_type', None)

    if scene_type == "opening_summary":
        img = _render_opening_summary(scene, w, h)
    elif scene_type == "summary_overview":
        img = _render_summary_overview(scene, w, h)
    elif scene_type == "signal":
        img = _render_signal(scene, w, h)
    elif scene_type == "supporting_notes":
        img = _render_supporting_notes(scene, w, h)
    elif scene_type == "closing_cta":
        img = _render_closing_cta(scene, w, h)
    elif scene_type == "cover":
        img = _render_cover(scene, w, h)
    else:
        img = _render_card(scene, w, h)

    try:
        img.save(str(output_path), format="PNG", optimize=True)
    except Exception as exc:
        raise RuntimeError(f"Failed to save scene image {output_path}: {exc}") from exc
