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


def _draw_bar_chart(draw: ImageDraw.Image, cx: int, top: int, total_w: int,
                    chart_h: int, items: list[tuple[str, int]]) -> int:
    """Draw a simple vertical bar chart centered on cx. Returns bottom y.

    items: list of (label, value). Bars scale to the max value; each bar shows
    its value above and a label below.
    """
    n = len(items)
    if n == 0:
        return top
    max_v = max((v for _, v in items), default=0) or 1
    slot = total_w // n
    bar_w = min(96, slot - 24)
    label_h = 30
    val_h = 28
    bar_zone = chart_h - label_h - val_h
    left = cx - total_w // 2
    val_font = _font(24, bold=True)
    label_font = _font(20)
    for i, (label, value) in enumerate(items):
        slot_cx = left + slot * i + slot // 2
        bh = int(bar_zone * (value / max_v)) if max_v else 0
        bh = max(bh, 4)
        bx0 = slot_cx - bar_w // 2
        by1 = top + val_h + bar_zone
        by0 = by1 - bh
        # value label above the bar
        vb = draw.textbbox((0, 0), str(value), font=val_font)
        draw.text((slot_cx - (vb[2] - vb[0]) // 2, by0 - val_h), str(value),
                  font=val_font, fill=C_TEXT)
        # bar (emerald gradient-ish: solid accent with a lighter cap)
        draw.rounded_rectangle([bx0, by0, bx0 + bar_w, by1], radius=8, fill=C_ACCENT)
        # label below
        lb = draw.textbbox((0, 0), label, font=label_font)
        draw.text((slot_cx - (lb[2] - lb[0]) // 2, by1 + 8), label,
                  font=label_font, fill=C_TEXT_MUTED)
    return top + chart_h


# ── Scene-specific renderers ──────────────────────────────────────────────────

def _render_opening_summary(scene, w: int, h: int) -> Image.Image:
    """Scene 1: Opening — brand + date + full report title + core count.

    Layout:
      top: brand header
      upper-mid: kicker + main title + (subtitle)
      mid: report core-count statement
      lower-mid: tagline
      bottom: footer
    """
    img = Image.new("RGBA", (w, h), C_BG)
    draw = _draw_background(img, w, h)

    header_y = _draw_brand_header(draw, w, getattr(scene, 'source_label', None))

    lines = getattr(scene, 'visual_lines', []) or ["今日 AI 前沿简报"]
    title_text = lines[0] if lines else "今日 AI 前沿简报"
    title_font = _font(54, bold=True)
    title_wrapped = _wrap_text(draw, title_text, title_font, w - 2 * SIDE_MARGIN - 40)[:3]
    sub_lines = list(lines[1:4])

    # Extract a headline count (e.g. "本期包含 6 个核心观察") for the big stat.
    import re as _re
    count = None
    for sl in sub_lines + [title_text]:
        m = _re.search(r"(\d+)", sl or "")
        if m:
            count = int(m.group(1)); break

    # Real stats (from the report) drive a bar chart; fall back to the ring.
    stats = (getattr(scene, 'metadata', {}) or {}).get("stats")
    chart_items: list[tuple[str, int]] = []
    if isinstance(stats, dict):
        chart_items = [
            ("新增", int(stats.get("new", 0))),
            ("已识别", int(stats.get("summarized", 0))),
            ("重要", int(stats.get("important", 0))),
            ("来源", int(stats.get("sources", 0))),
        ]

    # ── Measure the whole content block, then vertically center it ──
    kicker_h = 30 + 30
    title_h = len(title_wrapped) * 64
    chart_h = 260
    stat_h = (chart_h + 28) if chart_items else (200 if count else 0)
    # The sub-line ("接下来按顺序展开") duplicates the tagline below, so skip it
    # when the chart already fills the mid-section.
    show_sub = bool(sub_lines) and not chart_items
    sub_h = (len(sub_lines) * 42 + 24) if show_sub else 0
    tag_h = 60 + 30
    block_h = kicker_h + title_h + stat_h + sub_h + tag_h
    avail_top = header_y
    avail_bottom = h - BOTTOM_SAFE
    y = avail_top + max(40, (avail_bottom - avail_top - block_h) // 2)

    # Kicker
    _centered_text(draw, "AI FRONTIER RADAR", _font(24, bold=True), y, w, fill=C_ACCENT_2)
    y += kicker_h

    # Title
    for tl in title_wrapped:
        _centered_text(draw, tl, title_font, y, w)
        y += 64
    y += 24

    # Big stat graphic — a real bar chart when stats are available, else a ring
    # with the observation count.
    if chart_items:
        _draw_bar_chart(draw, w // 2, y, min(680, w - 2 * SIDE_MARGIN), chart_h, chart_items)
        y += stat_h  # includes a gap below the chart labels
    elif count:
        cx, cy, r = w // 2, y + 70, 64
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=C_ACCENT, width=6)
        nf = _font(64, bold=True)
        nb = draw.textbbox((0, 0), str(count), font=nf)
        draw.text((cx - (nb[2] - nb[0]) // 2, cy - (nb[3] - nb[1]) // 2 - nb[1]),
                  str(count), font=nf, fill=C_TEXT)
        # segmented bar under the ring, one segment per observation
        seg_total_w = min(560, count * 70)
        seg_w = seg_total_w // max(1, count) - 8
        sx = cx - seg_total_w // 2
        sby = cy + r + 26
        for i in range(count):
            col = C_ACCENT if i < count else C_TEXT_MUTED
            draw.rounded_rectangle([sx, sby, sx + seg_w, sby + 10], radius=5, fill=col)
            sx += seg_w + 8
        y += stat_h

    # Sub-lines (skipped when the chart is shown — see show_sub)
    if show_sub:
        for sl in sub_lines:
            _centered_text(draw, sl, _font(28), y, w, fill=C_TEXT_DIM)
            y += 42
        y += 24

    # Tagline
    _centered_text(draw, "接下来按顺序展开核心观察 · 完整报告见分享页",
                   _font(22), y + 30, w, fill=C_TEXT_MUTED)

    _draw_footer(draw, w, h)
    return img


def _render_summary_overview(scene, w: int, h: int) -> Image.Image:
    """Scene: Overview — the report's 总结 as ONE auto-fit, centered paragraph.

    Layout:
      top: brand header
      title: 今日整体判断 + kicker
      body: the full overview as a single flowing paragraph (font auto-fit so it
            fits one page), vertically centered, inside a soft panel
      bottom: footer
    """
    img = Image.new("RGBA", (w, h), C_BG)
    draw = _draw_background(img, w, h)
    header_y = _draw_brand_header(draw, w)

    # Page title + kicker
    title_font = _font(44, bold=True)
    title_text = getattr(scene, 'visual_title', '') or "今日整体判断"
    title_y = header_y + 20
    _centered_text(draw, title_text, title_font, title_y, w)
    _centered_text(draw, "TODAY'S OVERVIEW", _font(18), title_y + 58, w, fill=C_TEXT_MUTED)

    # The whole overview, joined into one paragraph.
    lines = getattr(scene, 'visual_lines', []) or [getattr(scene, 'visual_title', '')]
    paragraph = "".join(ln.strip() for ln in lines if ln and ln.strip())

    # Panel that fills the area below the title.
    card_top = title_y + 120
    card_bottom = h - BOTTOM_SAFE
    card_left = SIDE_MARGIN
    card_right = w - SIDE_MARGIN
    _draw_panel(draw, card_left, card_top, card_right, card_bottom, radius=20)

    inner_w = card_right - card_left - 80
    card_h = card_bottom - card_top
    # Largest font (within range) whose wrapped paragraph fits the panel.
    display_lines: list[str] = []
    body_size = 28
    for trial in (40, 36, 34, 32, 30, 28, 26):
        f = _font(trial)
        wrapped = _wrap_text(draw, paragraph, f, inner_w)
        if len(wrapped) * int(trial * 1.6) <= card_h - 72:
            body_size, display_lines = trial, wrapped
            break
    else:
        body_size = 26
        display_lines = _wrap_text(draw, paragraph, _font(26), inner_w)
    body_font = _font(body_size)
    line_h = int(body_size * 1.6)
    total_h = len(display_lines) * line_h
    ly = card_top + max(36, (card_h - total_h) // 2)
    for tl in display_lines:
        draw.text((card_left + 40, ly), tl, font=body_font, fill=C_TEXT)
        ly += line_h

    _draw_footer(draw, w, h)
    return img


def _render_signal(scene, w: int, h: int) -> Image.Image:
    """Core insight / signal page — one section per scene.

    Layout:
      top: CORE INSIGHT chip + section index chip + source label
      upper-mid: section title (full, no truncation)
      mid: bullet lines in a card panel (full sentences, no truncation)
      lower-mid: waveform decoration
      bottom: footer
    """
    img = Image.new("RGBA", (w, h), C_BG)
    draw = _draw_background(img, w, h)
    _draw_brand_header(draw, w)

    md = getattr(scene, 'metadata', {}) or {}

    # Top label row
    label_y = TOP_SAFE + 80
    # Section label chip — prefer storyboard's kicker
    kicker = md.get("kicker") if isinstance(md, dict) else None
    if not kicker:
        section_idx = md.get("section_index") if isinstance(md, dict) else None
        part = md.get("part") if isinstance(md, dict) else None
        if section_idx is not None and part is not None:
            kicker = f"CORE INSIGHT {section_idx:02d} · PART {part}"
        else:
            kicker = "CORE INSIGHT"
    _draw_chip(draw, kicker, SIDE_MARGIN, label_y, font_size=18)

    # Signal index (if available from metadata)
    section_idx = md.get("section_index") if isinstance(md, dict) else None
    if section_idx is not None:
        idx_label = f"#{section_idx}"
        _draw_chip(draw, idx_label, SIDE_MARGIN + 280, label_y, font_size=18,
                   bg=(59, 130, 246, 40), fg=C_ACCENT_2)

    # No separate signal title or source/依据: each core observation IS its
    # sentence, shown as the card body below. The kicker chip ("核心观察 N · 共M条")
    # already labels it, so the sentence reads once — no duplication.
    card_top = label_y + 64
    card_bottom = h - BOTTOM_SAFE - 100
    card_left = SIDE_MARGIN
    card_right = w - SIDE_MARGIN
    _draw_panel(draw, card_left, card_top, card_right, card_bottom, radius=20)

    # Explanation lines — full sentences, wrapped inside the panel, then the
    # whole block is vertically centered within the card so short bodies don't
    # leave the card mostly empty. Font scales up when there is plenty of room.
    body_lines = [ln.strip() for ln in getattr(scene, 'visual_lines', []) if ln.strip()][:5]
    inner_w = card_right - card_left - 70
    card_h = card_bottom - card_top
    # Pick the largest body font (within a range) whose wrapped block fits the card.
    body_size = 30
    for trial in (44, 40, 36, 32, 30):
        f = _font(trial)
        block = []
        for line in body_lines:
            block.extend(_wrap_text(draw, line, f, inner_w))
            block.append("")  # paragraph gap marker
        if block and block[-1] == "":
            block.pop()
        line_h = int(trial * 1.5)
        if len(block) * line_h <= card_h - 80:
            body_size, body_font, display_lines = trial, f, block
            break
    else:
        body_font = _font(30)
        display_lines = []
        for line in body_lines:
            display_lines.extend(_wrap_text(draw, line, body_font, inner_w))
            display_lines.append("")
        if display_lines and display_lines[-1] == "":
            display_lines.pop()
    line_h = int(body_size * 1.5)
    total_h = len(display_lines) * line_h
    line_y = card_top + max(28, (card_h - total_h) // 2)
    for wl in display_lines:
        if wl:
            wl_bbox = draw.textbbox((0, 0), wl, font=body_font)
            lx = (w - (wl_bbox[2] - wl_bbox[0])) // 2
            draw.text((lx, line_y), wl, font=body_font, fill=C_TEXT)
        line_y += line_h

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
      title: 补充观察 + page indicator
      body: bullet-like cards for each note (no truncation)
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

    # Page kicker (e.g. "MORE SIGNALS · 2/3")
    md = getattr(scene, 'metadata', {}) or {}
    page = md.get("page")
    total = md.get("total_pages")
    if page and total and total > 1:
        kicker_font = _font(18)
        _centered_text(
            draw,
            f"MORE SIGNALS · {page}/{total}",
            kicker_font,
            title_y + 60,
            w,
            fill=C_TEXT_MUTED,
        )

    # Items
    content_left = SIDE_MARGIN + 10
    content_right = w - SIDE_MARGIN - 10
    item_h = 110

    lines = getattr(scene, 'visual_lines', [])
    # Vertically center the item block in the area below the title.
    n_items = min(len(lines), 4)
    area_top = title_y + 110
    area_bottom = h - BOTTOM_SAFE
    content_top = area_top + max(0, (area_bottom - area_top - n_items * item_h) // 2)
    # Allow up to 4 items per page; wrap freely without truncation
    for idx, line in enumerate(lines[:4], start=1):
        iy = content_top + (idx - 1) * item_h
        # Number badge
        _draw_number_badge(draw, idx, content_left, iy)
        # Panel
        panel_left = content_left + 80
        panel_right = content_right
        panel_top = iy - 8
        panel_bottom = iy + 90
        _draw_panel(draw, panel_left, panel_top, panel_right, panel_bottom,
                    fill=C_PANEL_ALT, radius=12)
        # Text (full sentence, wraps inside panel)
        text_lines = _wrap_text(
            draw,
            line.strip(),
            _font(26),
            panel_right - panel_left - 30,
        )
        for t_idx, tl in enumerate(text_lines[:3]):
            ty = panel_top + 14 + t_idx * 38
            draw.text((panel_left + 14, ty), tl, font=_font(26), fill=C_TEXT)

    _draw_footer(draw, w, h)
    return img


def _render_closing_cta(scene, w: int, h: int) -> Image.Image:
    """Closing CTA — report summary + QR + share URL.

    Layout:
      top: brand header
      upper-mid: title + report summary lines (no truncation)
      mid: QR code (placeholder or real data URL) + share link
      bottom: footer
    """
    img = Image.new("RGBA", (w, h), C_BG)
    draw = _draw_background(img, w, h)
    _draw_brand_header(draw, w)

    title_font = _font(48, bold=True)
    title_text = getattr(scene, 'visual_title', '') or "查看完整报告"

    # Summary lines from visual_lines (without scan/share lines)
    summary_lines = [
        ln for ln in (getattr(scene, 'visual_lines', []) or [])
        if ln and "扫码" not in ln and "访问" not in ln
    ][:4]

    md = getattr(scene, 'metadata', {}) or {}
    qr_data_url = md.get("qr_code_data_url")
    share_url = md.get("share_url")
    qr_size = 240

    # Measure the whole block and vertically center it (no top-anchored gap).
    sum_font = _font(26)
    title_h = 70
    sum_h = len(summary_lines) * 42 + (24 if summary_lines else 0)
    qr_block_h = 30 + qr_size
    url_h = 50 if share_url else 0
    hint_h = 44
    block_h = title_h + sum_h + qr_block_h + url_h + hint_h
    avail_top = TOP_SAFE + 60
    avail_bottom = h - BOTTOM_SAFE
    y = avail_top + max(20, (avail_bottom - avail_top - block_h) // 2)

    # Title
    _centered_text(draw, title_text, title_font, y, w)
    y += title_h

    # Summary lines
    for sl in summary_lines:
        _centered_text(draw, sl, sum_font, y, w, fill=C_TEXT_DIM)
        y += 42
    if summary_lines:
        y += 24

    # QR + share link block
    block_top = y + 30
    qr_left = (w - qr_size) // 2
    qr_top = block_top
    qr_right = qr_left + qr_size
    qr_bottom = qr_top + qr_size

    # Draw QR placeholder
    _draw_panel(draw, qr_left, qr_top, qr_right, qr_bottom,
                fill=(15, 23, 42, 200), outline=C_CARD_BORDER, radius=16)
    if qr_data_url and isinstance(qr_data_url, str) and qr_data_url.startswith("data:image"):
        # Real QR data URL — try to decode and paste
        try:
            import base64
            from io import BytesIO
            import re as _re
            m = _re.match(r"data:image/(png|jpeg);base64,(.+)", qr_data_url)
            if m:
                img_bytes = base64.b64decode(m.group(2))
                qr_img = Image.open(BytesIO(img_bytes)).convert("RGBA")
                qr_img = qr_img.resize((qr_size - 16, qr_size - 16))
                img.paste(qr_img, (qr_left + 8, qr_top + 8), qr_img)
            else:
                _draw_qr_label(draw, qr_left, qr_top, qr_right, qr_bottom)
        except Exception:
            _draw_qr_label(draw, qr_left, qr_top, qr_right, qr_bottom)
    else:
        _draw_qr_label(draw, qr_left, qr_top, qr_right, qr_bottom)

    # Share URL
    if share_url:
        url_font = _font(20)
        url_y = qr_bottom + 24
        url_text = str(share_url)
        url_bbox = draw.textbbox((0, 0), url_text, font=url_font)
        ux = (w - (url_bbox[2] - url_bbox[0])) // 2
        # Truncate display if too long, but keep the visible form
        max_url_chars = 36
        if len(url_text) > max_url_chars:
            url_text = url_text[: max_url_chars - 1] + "…"
            url_bbox = draw.textbbox((0, 0), url_text, font=url_font)
            ux = (w - (url_bbox[2] - url_bbox[0])) // 2
        draw.text((ux, url_y), url_text, font=url_font, fill=C_ACCENT_2)

    # Hint text
    hint_font = _font(18)
    hint_y = qr_bottom + (24 + 30 if share_url else 24)
    hint_text = "完整报告包含全文、来源链接和语音播报"
    _centered_text(draw, hint_text, hint_font, hint_y, w, fill=C_TEXT_MUTED)

    _draw_footer(draw, w, h)
    return img


def _draw_qr_label(draw, qr_left, qr_top, qr_right, qr_bottom) -> None:
    """Draw a placeholder QR label inside the QR panel."""
    qr_label = "[ 扫码区域 ]"
    qr_label_font = _font(20)
    qlbbox = draw.textbbox((0, 0), qr_label, font=qr_label_font)
    qlx = ((qr_left + qr_right) - (qlbbox[2] - qlbbox[0])) // 2
    qly = (qr_top + qr_bottom - (qlbbox[3] - qlbbox[1])) // 2
    draw.text((qlx, qly), qr_label, font=qr_label_font, fill=C_TEXT_MUTED)


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

    if scene_type in ("opening_summary", "opening"):
        img = _render_opening_summary(scene, w, h)
    elif scene_type in ("summary_overview", "overview_paged"):
        img = _render_summary_overview(scene, w, h)
    elif scene_type in ("signal", "core_insight", "core_insight_continuation"):
        img = _render_signal(scene, w, h)
    elif scene_type == "supporting_notes":
        img = _render_supporting_notes(scene, w, h)
    elif scene_type in ("closing_cta", "closing"):
        img = _render_closing_cta(scene, w, h)
    elif scene_type == "cover":
        img = _render_cover(scene, w, h)
    else:
        img = _render_card(scene, w, h)

    try:
        img.save(str(output_path), format="PNG", optimize=True)
    except Exception as exc:
        raise RuntimeError(f"Failed to save scene image {output_path}: {exc}") from exc
