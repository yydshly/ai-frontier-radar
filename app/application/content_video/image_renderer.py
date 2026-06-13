"""content_video — Pillow-based scene image renderer.

Renders each VideoScene into a 1080x1920 PNG using Pillow.
V1 uses a fixed dark tech-style template — no browser, no html2canvas.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

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


def _load_font(size: int, *, fallback: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a proportional font. Falls back to default if font file unavailable."""
    # Try system fonts first (works on Linux/macOS/Windows)
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:\\Windows\\Fonts\\seguisb.ttf",   # Segoe UI Semibold (Windows)
        "C:\\Windows\\Fonts\\msyh.ttc",      # Microsoft YaHei (fallback)
    ]
    for fp in font_paths:
        try:
            return ImageFont.truetype(fp, size)
        except Exception:
            continue
    # Pillow default
    return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
               max_width: int, line_height: int) -> list[str]:
    """Wrap text into lines that fit within max_width pixels."""
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


def _choose_font_size(draw: ImageDraw.ImageDraw, text: str, max_width: int,
                      min_size: int, max_size: int) -> int:
    """Binary-search for the largest font size that fits max_width."""
    lo, hi = min_size, max_size
    best = min_size
    while lo <= hi:
        mid = (lo + hi) // 2
        font = _load_font(mid)
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _render_cover(scene, w: int, h: int) -> Image.Image:
    """Render a cover scene."""
    img = Image.new("RGBA", (w, h), C_BG)
    draw = ImageDraw.Draw(img)

    title_font = _load_font(64, fallback=True)
    subtitle_font = _load_font(32)
    date_font = _load_font(28)

    # Brand label top-left
    brand = "◎ AI 前沿雷达"
    draw.text((60, 60), brand, font=title_font, fill=C_ACCENT)

    # Date top-right
    if scene.visual_lines and len(scene.visual_lines) >= 3:
        date_text = scene.visual_lines[2]
        d_bbox = draw.textbbox((0, 0), date_text, font=date_font)
        draw.text((w - d_bbox[2] - 60, 60), date_text, font=date_font, fill=C_SOURCE)

    # Horizontal rule
    draw.rectangle([(60, 145), (w - 60, 148)], fill=C_ACCENT)

    # Title block
    title_text = scene.visual_lines[0] if scene.visual_lines else scene.visual_title
    title_size = _choose_font_size(draw, title_text, w - 120, 36, 80)
    title_font_used = _load_font(title_size)
    bbox = draw.textbbox((0, 0), title_text, font=title_font_used)
    title_y = 200
    draw.text(((w - bbox[2]) // 2, title_y), title_text, font=title_font_used, fill=C_TEXT)

    # Subtitle
    if len(scene.visual_lines) > 1:
        sub_text = scene.visual_lines[1]
        sub_font = _load_font(36)
        bbox2 = draw.textbbox((0, 0), sub_text, font=sub_font)
        draw.text(((w - bbox2[2]) // 2, title_y + bbox[3] - bbox[1] + 30), sub_text,
                  font=sub_font, fill=C_TEXT_DIM)

    # Bottom tagline
    tagline = "扫码查看完整报告 · 语音播报 · 全部文章原文"
    tag_font = _load_font(24)
    tag_bbox = draw.textbbox((0, 0), tagline, font=tag_font)
    draw.text(((w - tag_bbox[2]) // 2, h - tag_bbox[3] - 60), tagline,
              font=tag_font, fill=C_SOURCE)

    # Auto-gen footer
    footer = "AI Frontier Radar · 视频由系统自动生成"
    ft_bbox = draw.textbbox((0, 0), footer, font=tag_font)
    draw.text(((w - ft_bbox[2]) // 2, h - ft_bbox[3] - 30), footer,
              font=tag_font, fill=C_SOURCE)

    return img


def _render_card(scene, w: int, h: int, title_color=C_ACCENT) -> Image.Image:
    """Render a generic content card scene (summary/highlight/takeaways)."""
    img = Image.new("RGBA", (w, h), C_BG)
    draw = ImageDraw.Draw(img)

    MARGIN = 60
    content_w = w - 2 * MARGIN

    y = 80

    # Section title (small caps label)
    label_text = scene.scene_type.upper()
    if scene.scene_type == "highlight":
        label_text = "重点内容"
    elif scene.scene_type == "summary":
        label_text = "核心判断"
    elif scene.scene_type == "takeaways":
        label_text = "今日要点"
    elif scene.scene_type == "ending":
        label_text = "结语"

    label_font = _load_font(22)
    draw.text((MARGIN, y), label_text, font=label_font, fill=title_color)
    y += 50

    # Divider
    draw.rectangle([(MARGIN, y), (w - MARGIN, y + 3)], fill=title_color)
    y += 30

    # Visual title
    vt_font_size = _choose_font_size(draw, scene.visual_title, content_w, 32, 64)
    vt_font = _load_font(vt_font_size)
    vt_bbox = draw.textbbox((0, 0), scene.visual_title, font=vt_font)
    draw.text((MARGIN, y), scene.visual_title, font=vt_font, fill=C_TEXT)
    y += vt_bbox[3] - vt_bbox[1] + 20

    # Visual lines (body)
    body_font = _load_font(34)
    line_height = 56
    for line in scene.visual_lines[:6]:
        line = line.strip()
        if not line:
            continue
        wrapped = _wrap_text(draw, line, body_font, content_w, line_height)
        for wl in wrapped:
            draw.text((MARGIN, y), wl, font=body_font, fill=C_TEXT_DIM)
            y += line_height
        y += 10

    # Source label bottom-right
    if scene.source_label:
        src_font = _load_font(24)
        draw.text((w - MARGIN, h - 80), scene.source_label, font=src_font, fill=C_SOURCE)

    # Footer
    footer = "AI Frontier Radar · 视频由系统自动生成"
    ft_font = _load_font(20)
    ft_bbox = draw.textbbox((0, 0), footer, font=ft_font)
    draw.text(((w - ft_bbox[2]) // 2, h - ft_bbox[3] - 30), footer,
              font=ft_font, fill=C_SOURCE)

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
