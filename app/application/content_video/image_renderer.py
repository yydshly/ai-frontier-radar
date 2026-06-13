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
    """Render a cover scene — simplified: brand, date, signal count.

    New cover structure (no long title):
      - Brand: ◎ AI 前沿雷达
      - Date + signal count from visual_lines
      - Short tagline
    """
    img = Image.new("RGBA", (w, h), C_BG)
    draw = ImageDraw.Draw(img)

    # Use bold for brand and date; regular for subtitle lines
    brand_font = _load_font(52, bold=True)
    date_font = _load_font(30)
    tagline_font = _load_font(26)

    # Brand label centered top
    brand = "◎ AI 前沿雷达"
    brand_bbox = draw.textbbox((0, 0), brand, font=brand_font)
    draw.text(((w - brand_bbox[2]) // 2, 80), brand, font=brand_font, fill=C_ACCENT)

    # Horizontal accent rule below brand
    draw.rectangle([(w // 4, 148), (w - w // 4, 151)], fill=C_ACCENT)

    # Visual lines: usually [date_label, "N 个重点信号", ...]
    # Show first 2 lines centered
    line_y = 200
    for vl in (scene.visual_lines or [])[:2]:
        vl = vl.strip()
        if not vl:
            continue
        vl_font = _choose_font_size(draw, vl, w - 160, 24, 54)
        vl_font_obj = _load_font(vl_font)
        vl_bbox = draw.textbbox((0, 0), vl, font=vl_font_obj)
        draw.text(((w - vl_bbox[2]) // 2, line_y), vl, font=vl_font_obj, fill=C_TEXT)
        line_y += vl_bbox[3] - vl_bbox[1] + 24

    # Bottom tagline
    tagline = "扫码查看完整报告 · 语音播报 · 全部文章原文"
    tag_bbox = draw.textbbox((0, 0), tagline, font=tagline_font)
    draw.text(((w - tag_bbox[2]) // 2, h - tag_bbox[3] - 70), tagline,
              font=tagline_font, fill=C_SOURCE)

    # Auto-gen footer
    footer = "AI Frontier Radar · 视频由系统自动生成"
    ft_bbox = draw.textbbox((0, 0), footer, font=tagline_font)
    draw.text(((w - ft_bbox[2]) // 2, h - ft_bbox[3] - 35), footer,
              font=tagline_font, fill=C_SOURCE)

    return img


def _render_card(scene, w: int, h: int, title_color=C_ACCENT) -> Image.Image:
    """Render a generic content card scene (summary/highlight/takeaways/ending)."""
    img = Image.new("RGBA", (w, h), C_BG)
    draw = ImageDraw.Draw(img)

    # Wider margins → narrower content for mobile readability
    MARGIN = 72
    content_w = w - 2 * MARGIN
    # Safety zone: don't draw below this y
    BOTTOM_SAFE = h - 120

    y = 80

    # Section title (small caps label, bold)
    label_text = scene.scene_type.upper()
    if scene.scene_type == "highlight":
        label_text = "信号"
    elif scene.scene_type == "highlight_detail":
        label_text = "重点"
    elif scene.scene_type == "summary":
        label_text = "总判断"
    elif scene.scene_type == "takeaways":
        label_text = "今日结论"
    elif scene.scene_type == "ending":
        label_text = "结语"

    label_font = _load_font(20, bold=True)
    draw.text((MARGIN, y), label_text, font=label_font, fill=title_color)
    y += 48

    # Divider
    draw.rectangle([(MARGIN, y), (w - MARGIN, y + 3)], fill=title_color)
    y += 28

    # Visual title (bold) — only if not cover
    if scene.visual_title and scene.scene_type != "cover":
        vt_font_size = _choose_font_size(draw, scene.visual_title, content_w, 30, 54, bold=True)
        vt_font = _load_font(vt_font_size, bold=True)
        vt_bbox = draw.textbbox((0, 0), scene.visual_title, font=vt_font)
        # Check bounds
        if y + (vt_bbox[3] - vt_bbox[1]) < BOTTOM_SAFE:
            draw.text((MARGIN, y), scene.visual_title, font=vt_font, fill=C_TEXT)
            y += vt_bbox[3] - vt_bbox[1] + 16

    # Visual lines (body, regular weight) — smaller font, tighter line height
    body_font = _load_font(32)
    line_height = 52  # ~1.6x for readability
    for line in scene.visual_lines[:5]:
        line = line.strip()
        if not line:
            continue
        wrapped = _wrap_text(draw, line, body_font, content_w, line_height)
        for wl in wrapped:
            if y + line_height > BOTTOM_SAFE:
                # Draw ellipsis and stop
                draw.text((MARGIN, y), "…", font=body_font, fill=C_TEXT_DIM)
                y += line_height
                break
            draw.text((MARGIN, y), wl, font=body_font, fill=C_TEXT_DIM)
            y += line_height
        y += 8

    # Source label bottom-right
    if scene.source_label:
        src_font = _load_font(22)
        draw.text((w - MARGIN, h - 80), scene.source_label, font=src_font, fill=C_SOURCE)

    # Footer
    footer = "AI Frontier Radar · 视频由系统自动生成"
    ft_font = _load_font(18)
    ft_bbox = draw.textbbox((0, 0), footer, font=ft_font)
    ft_y = h - ft_bbox[3] - 30
    if ft_y > y + 10:  # only if there's room
        draw.text(((w - ft_bbox[2]) // 2, ft_y), footer, font=ft_font, fill=C_SOURCE)

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
