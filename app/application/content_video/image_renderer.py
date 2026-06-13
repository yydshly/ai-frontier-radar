"""content_video — Pillow-based scene image renderer.

Renders each VideoScene into a 1080x1920 PNG using Pillow.
V1 uses a fixed dark tech-style template — no browser, no html2canvas.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from app.application.content_video.fonts import load_cjk_font

# Default output size (9:16 portrait)
DEFAULT_W = 1080
DEFAULT_H = 1920

# Colour palette (dark tech theme)
C_BG = (8, 15, 24)           # #080f18
C_CARD_BG = (13, 23, 35)     # #0d1723
C_ACCENT = (52, 211, 153)     # #34D399
C_ACCENT_DIM = (52, 211, 153, 25)  # transparent accent fill
C_TEXT = (234, 241, 246)      # #eaf1f6
C_TEXT_DIM = (196, 210, 221)  # #c4d2dd
C_SOURCE = (127, 149, 164)    # #7f95a4
C_DIVIDER = (255, 255, 255, 19)  # rgba white 12%
C_TAG = (52, 211, 153, 30)


def _load_font(size: int, *, bold: bool = False):
    """Load a CJK-capable font at the given size.

    Uses load_cjk_font which raises ContentVideoFontError on failure —
    no silent fallback to load_default() (which would render boxes).
    """
    return load_cjk_font(size, bold=bold)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, line_height: int) -> list[str]:
    """Wrap text into lines that fit within max_width pixels.

    Handles both space-separated words (English) and continuous text (Chinese)
    by accumulating characters and measuring width via textbbox.
    """
    # Fast path: if text has spaces, use word-based wrap
    if " " in text:
        words = text.split()
        lines = []
        current = ""
        for word in words:
            test = (current + " " + word).strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            w = bbox[2] - bbox[0]
            if w <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    # Chinese / continuous text: character-level wrap
    lines = []
    current = ""
    for char in text:
        test = current + char
        bbox = draw.textbbox((0, 0), test, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def _choose_font_size(draw: ImageDraw.ImageDraw, text: str, max_width: int,
                      min_size: int, max_size: int, *, bold: bool = False) -> int:
    """Binary-search for the largest font size that fits max_width."""
    lo, hi = min_size, max_size
    best = min_size
    while lo <= hi:
        mid = (lo + hi) // 2
        font = _load_font(mid, bold=bold)
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _render_cover(scene, w: int, h: int) -> Image.Image:
    """Render a cover scene — vertically centered, minimal.

    Structure:
      - Brand centered near top
      - Visual lines centered in middle
      - Tagline and footer centered at bottom
    """
    img = Image.new("RGBA", (w, h), C_BG)
    draw = ImageDraw.Draw(img)

    brand_font = _load_font(50, bold=True)
    tagline_font = _load_font(24)

    # Brand centered in top 25%
    brand = "◎ AI 前沿雷达"
    brand_bbox = draw.textbbox((0, 0), brand, font=brand_font)
    brand_x = (w - brand_bbox[2]) // 2
    draw.text((brand_x, 60), brand, font=brand_font, fill=C_ACCENT)

    # Accent rule below brand
    draw.rectangle([(w // 4, 130), (w - w // 4, 133)], fill=C_ACCENT)

    # Visual lines: date + signal count — centered in middle of card
    mid_start = int(h * 0.30)
    mid_end = int(h * 0.65)
    line_y = mid_start
    for vl in (scene.visual_lines or [])[:2]:
        vl = vl.strip()
        if not vl:
            continue
        vl_font = _choose_font_size(draw, vl, w - 120, 24, 52)
        vl_font_obj = _load_font(vl_font)
        vl_bbox = draw.textbbox((0, 0), vl, font=vl_font_obj)
        vl_x = (w - vl_bbox[2]) // 2
        draw.text((vl_x, line_y), vl, font=vl_font_obj, fill=C_TEXT)
        line_y += vl_bbox[3] - vl_bbox[1] + 20

    # Tagline centered above footer
    tagline = "扫码查看完整报告 · 语音播报 · 全部文章原文"
    tag_bbox = draw.textbbox((0, 0), tagline, font=tagline_font)
    tag_x = (w - tag_bbox[2]) // 2
    draw.text((tag_x, mid_end), tagline, font=tagline_font, fill=C_SOURCE)

    # Footer centered at very bottom
    footer = "AI Frontier Radar · 视频由系统自动生成"
    ft_bbox = draw.textbbox((0, 0), footer, font=tagline_font)
    ft_x = (w - ft_bbox[2]) // 2
    draw.text((ft_x, h - ft_bbox[3] - 20), footer, font=tagline_font, fill=C_SOURCE)

    return img


def _render_card(scene, w: int, h: int, title_color=C_ACCENT) -> Image.Image:
    """Render a generic content card scene (signal/summary/takeaways/ending).

    Layout: vertically centered card area with semi-transparent card background.
    """
    img = Image.new("RGBA", (w, h), C_BG)
    draw = ImageDraw.Draw(img)

    # Layout constants
    SIDE_MARGIN = 72
    content_w = w - 2 * SIDE_MARGIN
    BOTTOM_SAFE = h - 110

    # ── Semi-transparent card background ─────────────────────────────────────
    # Draw a subtle rounded card area in the center 60% of the image
    card_top = int(h * 0.18)
    card_bottom = int(h * 0.82)
    card_left = SIDE_MARGIN
    card_right = w - SIDE_MARGIN

    # Subtle card fill
    draw.rounded_rectangle(
        [card_left, card_top, card_right, card_bottom],
        radius=24,
        fill=(255, 255, 255, 8),
    )
    # Subtle card border
    draw.rounded_rectangle(
        [card_left, card_top, card_right, card_bottom],
        radius=24,
        outline=(52, 211, 153, 38),
        width=1,
    )

    # ── Label (top-left of card) ───────────────────────────────────────────
    label_text = scene.scene_type.upper()
    if scene.scene_type == "signal":
        label_text = "信号"
    elif scene.scene_type == "summary":
        label_text = "总判断"
    elif scene.scene_type == "takeaways":
        label_text = "今日结论"
    elif scene.scene_type == "ending":
        label_text = "结语"

    label_font = _load_font(18, bold=True)
    draw.text((SIDE_MARGIN + 20, card_top + 20), label_text, font=label_font, fill=title_color)

    # ── Visual title (centered in card) ─────────────────────────────────
    y = card_top + 70

    if scene.visual_title and scene.scene_type != "cover":
        vt_font_size = _choose_font_size(draw, scene.visual_title, content_w - 40, 28, 56, bold=True)
        vt_font = _load_font(vt_font_size, bold=True)
        vt_bbox = draw.textbbox((0, 0), scene.visual_title, font=vt_font)
        vt_x = (w - vt_bbox[2]) // 2
        draw.text((vt_x, y), scene.visual_title, font=vt_font, fill=C_TEXT)
        y += vt_bbox[3] - vt_bbox[1] + 24

    # ── Visual lines (centered body text) ──────────────────────────────────
    body_font = _load_font(30)
    line_height = 50  # ~1.65x for readability

    for line in scene.visual_lines[:4]:
        line = line.strip()
        if not line:
            continue
        wrapped = _wrap_text(draw, line, body_font, content_w - 40, line_height)
        for wl in wrapped:
            if y + line_height > card_bottom - 20:
                draw.text((SIDE_MARGIN + 20, y), "…", font=body_font, fill=C_TEXT_DIM)
                y += line_height
                break
            wl_bbox = draw.textbbox((0, 0), wl, font=body_font)
            wl_x = (w - wl_bbox[2]) // 2
            draw.text((wl_x, y), wl, font=body_font, fill=C_TEXT_DIM)
            y += line_height
        y += 6  # small gap between lines

    # ── Source label (bottom-right of card) ────────────────────────────────
    if scene.source_label:
        src_font = _load_font(20)
        src_bbox = draw.textbbox((0, 0), scene.source_label, font=src_font)
        draw.text((card_right - src_bbox[2] - 10, card_bottom - 36), scene.source_label, font=src_font, fill=C_SOURCE)

    # ── Footer (centered at very bottom) ────────────────────────────────
    footer = "AI Frontier Radar · 视频由系统自动生成"
    ft_font = _load_font(16)
    ft_bbox = draw.textbbox((0, 0), footer, font=ft_font)
    ft_x = (w - ft_bbox[2]) // 2
    draw.text((ft_x, h - ft_bbox[3] - 16), footer, font=ft_font, fill=C_SOURCE)

    return img


def render_scene_image(scene, output_path: Path, *, size: str = "1080x1920") -> None:
    """Render a VideoScene to a PNG file.

    Raises RuntimeError on rendering failure.
    """
    try:
        w_str, h_str = size.split("x")
        w, h = int(w_str), int(h_str)
    except (ValueError, AttributeError):
        w, h = DEFAULT_W, DEFAULT_H

    if scene.scene_type == "cover":
        img = _render_cover(scene, w, h)
    else:
        img = _render_card(scene, w, h)

    try:
        img.save(str(output_path), format="PNG", optimize=True)
    except Exception as exc:
        raise RuntimeError(f"Failed to save scene image {output_path}: {exc}") from exc
