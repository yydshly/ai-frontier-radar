"""content_video — Text compaction utilities for short-form video scenes.

Provides pure string-manipulation helpers to shorten text for mobile-friendly
scene cards without calling any LLM or external service.
"""
from __future__ import annotations


def compact_title(text: str, max_chars: int = 22) -> str:
    """Shorten a title to at most max_chars characters.

    Truncates with '…' if over limit.
    Preserves Chinese characters and ASCII.
    """
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    # Find a cut point that respects character boundary
    # For mixed content, just use max_chars as a rough guide
    return text[: max_chars - 1] + "…"


def compact_line(text: str, max_chars: int = 36) -> str:
    """Shorten a body line to at most max_chars characters."""
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def split_to_visual_lines(
    text: str,
    max_lines: int = 3,
    max_chars_per_line: int = 28,
) -> list[str]:
    """Split a block of text into short visual lines for a scene card.

    Does not call any LLM — pure character-level splitting.
    Tries to break at natural pauses (，。；) before max_chars is exceeded.
    Falls back to character-level wrap if no punctuation within limit.
    """
    if not text:
        return []
    text = text.strip()
    if not text:
        return []

    result: list[str] = []

    # Try to split by sentences first (Chinese punctuation)
    import re as _re

    # Split on Chinese + English sentence-ending punctuation
    sentences: list[str] = _re.split(r"(?<=[，。；！？、])", text)
    # Remove empties
    sentences = [s.strip() for s in sentences if s.strip()]

    current_line = ""

    for sentence in sentences:
        # Check if adding this sentence would exceed max_chars_per_line
        test = current_line + sentence if not current_line else current_line + "，" + sentence
        if len(test) <= max_chars_per_line and len(result) < max_lines - 1:
            current_line = test
        else:
            # Commit current line if non-empty
            if current_line:
                result.append(current_line)
            # Start new line with this sentence (truncated if needed)
            if len(result) >= max_lines:
                break
            if len(sentence) <= max_chars_per_line:
                current_line = sentence
            else:
                # Character-level fallback for long sentence
                chars = []
                for ch in sentence:
                    chars.append(ch)
                    line_so_far = "".join(chars)
                    if len(line_so_far) >= max_chars_per_line:
                        result.append("".join(chars[:-1]) + "…")
                        chars = [ch]
                        if len(result) >= max_lines:
                            break
                if chars and len(result) < max_lines:
                    current_line = "".join(chars)

    # Don't forget the last line
    if current_line and len(result) < max_lines:
        result.append(current_line)

    return result[:max_lines]


def compact_narration(text: str, max_chars: int = 120) -> str:
    """Shorten narration text to at most max_chars for TTS."""
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


# ── Video language helpers ─────────────────────────────────────────────────────────

def to_video_signal_title(title: str, max_chars: int = 18) -> str:
    """Convert a signal title to short, punchy video title.

    Examples:
      "Agent Safety Evaluations Are Becoming a Key Focus"
        → "Agent 安全评估成为焦点"

    Rules (no LLM — pure text rules):
      - Strip prefix verbs: "研究", "发现", "证明" etc.
      - Keep the core noun phrase
      - Cap at max_chars
    """
    if not title:
        return ""
    title = title.strip()

    # Strip common report-style prefixes
    prefixes = [
        "研究发现",
        "研究显示",
        "研究表表明",
        "数据显示",
        "报告指出",
        "文章称",
        "据悉",
        "根据",
        "通过",
        "实现",
        "成功",
        "首次",
    ]
    for p in prefixes:
        if title.startswith(p):
            title = title[len(p):].strip()
            if title:
                break

    # Strip trailing punctuation
    title = title.rstrip("，。、；：")

    # Cap length
    if len(title) > max_chars:
        return title[:max_chars - 1] + "…"
    return title


def to_video_explanation_lines(
    summary: str | None,
    why_it_matters: str | None,
    key_points: list[str],
    max_lines: int = 3,
    max_chars_per_line: int = 24,
) -> list[str]:
    """Convert section content into 1-3 punchy explanation lines for a signal card.

    Output is short, conversational, and suitable for a mobile video card.
    Not a direct summary — sentences are restructured for spoken delivery.

    Returns a list of up to max_lines short Chinese lines.
    """
    # Collect candidate source lines
    candidates: list[str] = []

    if why_it_matters:
        # Split why_it_matters into sentences, compact each
        import re as _re
        parts = _re.split(r"(?<=[，。；！？、])", why_it_matters)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # Strip leading conjunctions
            for prefix in ("因为", "由于", "所以", "这说明", "这表明", "这意味着"):
                if part.startswith(prefix):
                    part = part[len(prefix):].strip()
            if part:
                candidates.append(part)
    elif summary:
        # Fallback: use first sentence of summary
        import re as _re
        parts = _re.split(r"(?<=[，。；！？])", summary)
        if parts:
            first = parts[0].strip()
            if first:
                candidates.append(first)

    # If still empty, use key_points
    if not candidates and key_points:
        for kp in key_points[:2]:
            kp = kp.strip()
            if kp:
                candidates.append(kp)

    # Build short lines using split_to_visual_lines on the candidates
    combined = "。".join(candidates)
    lines = split_to_visual_lines(combined, max_lines=max_lines, max_chars_per_line=max_chars_per_line)
    return [ln.strip() for ln in lines if ln.strip()]


def to_video_narration(
    index: int,
    title: str,
    summary: str | None,
    why_it_matters: str | None,
    *,
    max_chars: int = 90,
) -> str:
    """Build a short, spoken narration for a signal scene.

    Structure: "第N个信号是：{title}。{concise explanation}。"
    Total cap: max_chars characters.
    """
    label = _cn_number(index) if 1 <= index <= 10 else str(index)
    title_part = f"第{label}个信号是：{to_video_signal_title(title, 20)}"

    # Build explanation from why_it_matters or summary
    explanation_parts: list[str] = []
    if why_it_matters:
        # Take first sentence of why_it_matters, compact
        import re as _re
        sentences = _re.split(r"(?<=[，。；！？])", why_it_matters)
        if sentences:
            first = sentences[0].strip()
            # Strip leading conjunction
            for prefix in ("因为", "由于", "这说明", "这表明"):
                if first.startswith(prefix):
                    first = first[len(prefix):].strip()
            if first:
                explanation_parts.append(first)
    elif summary:
        # Take first sentence
        import re as _re
        sentences = _re.split(r"(?<=[，。；！？])", summary)
        if sentences:
            first = sentences[0].strip()
            if first:
                explanation_parts.append(first)

    explanation_text = "。".join(explanation_parts)
    if explanation_text:
        full = f"{title_part}。{explanation_text}。"
    else:
        full = title_part + "。"

    return compact_narration(full, max_chars=max_chars)


def split_highlight_scenes(
    section,
    scene_index: int,
    *,
    max_chars_title: int = 22,
    max_chars_body: int = 36,
) -> list[dict]:
    """Split a single highlight/section into 1–2 scenes: title + why-it-matters.

    Returns a list of scene dicts ready for VideoScene construction.
    """
    scenes = []

    # ── Scene A: Signal title page ────────────────────────────────────────────
    title = compact_title(section.title, max_chars=max_chars_title)
    if section.summary:
        summary_line = compact_line(section.summary, max_chars=max_chars_body)
    else:
        summary_line = None

    visual_lines = [title]
    if summary_line:
        visual_lines.append(summary_line)

    scenes.append({
        "scene_type": "highlight",
        "visual_title": title,
        "visual_lines": visual_lines,
        "narration_prefix": f"第{_cn_number(scene_index)}个值得关注的信号是：",
    })

    # ── Scene B: Why it matters ──────────────────────────────────────────────
    if section.why_it_matters:
        why_lines = split_to_visual_lines(
            section.why_it_matters,
            max_lines=3,
            max_chars_per_line=max_chars_body,
        )
        if why_lines:
            scenes.append({
                "scene_type": "highlight_detail",
                "visual_title": "为什么重要",
                "visual_lines": why_lines,
                "narration_prefix": "这值得关注，因为",
            })
    elif section.key_points:
        # Fallback: use first key point as explanation
        kp = section.key_points[0]
        kp_line = compact_line(kp, max_chars=max_chars_body)
        scenes.append({
            "scene_type": "highlight_detail",
            "visual_title": "为什么重要",
            "visual_lines": [kp_line],
            "narration_prefix": "原因是：",
        })

    return scenes


# ── helpers ───────────────────────────────────────────────────────────────────

_CHINESE_DIGITS = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]


def _cn_number(n: int) -> str:
    if 1 <= n <= 10:
        return _CHINESE_DIGITS[n]
    return str(n)
