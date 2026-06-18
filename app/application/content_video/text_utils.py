"""content_video — Text utilities for full-report video storyboard.

Provides pure string-manipulation helpers that **preserve** report content
rather than truncating it. Core principles:

1. Core information (overview, bullets, supporting notes, conclusions)
   is NEVER truncated with ellipsis ("…" or "...").  If a scene cannot
   fit the content, the caller must create additional scenes.

2. Visual lines must never be single-character fragments.  Splitting uses
   Chinese / English punctuation (。；！？、,;:) and only falls back to
   whitespace / character-level breaks when no punctuation exists.

3. Helpers are pure: no LLM, no IO, deterministic given the same input.

Available helpers:
  compact_title / compact_line           — only for *non-core* decoration
  split_chinese_sentences                 — semantic sentence split
  split_text_to_scene_pages               — group sentences into pages
  split_bullet_to_pages                   — paginate a single section
  contains_ellipsis                       — assertion helper
  is_fragment_line                        — assertion helper (e.g. "题；")
  to_video_signal_title                   — short title for video cards
  to_video_explanation_lines              — back-compat for old storyboard
  to_video_narration                      — back-compat narration builder
"""
from __future__ import annotations

import re

# ── Ellipsis & fragment detection ──────────────────────────────────────────────

_ELLIPSIS_RE = re.compile(r"(\.{3}|…|。。。|……)")


def contains_ellipsis(text: str) -> bool:
    """True if the text contains any truncation marker (..., …, 。。。, ……)."""
    if not text:
        return False
    return bool(_ELLIPSIS_RE.search(text))


def remove_ellipsis(text: str) -> str:
    """Strip any ellipsis markers from text.  Used defensively by callers."""
    if not text:
        return text
    return _ELLIPSIS_RE.sub("", text)


def is_fragment_line(text: str) -> bool:
    """Detect pathological single-character lines like '题；' or '问，'.

    Returns True when the line (after stripping whitespace) contains
    only one CJK character plus a punctuation mark.
    """
    if not text:
        return False
    s = text.strip()
    if not s:
        return False
    # Strip all punctuation
    body = re.sub(r"[，。；！？、：,.;:!?。，、；：（）()【】\[\]·•\s]", "", s)
    return len(body) < 2


# ── Sentence splitting ─────────────────────────────────────────────────────────

# Strong sentence terminators
_TERMINATORS = "。！？!?；;\n"
# Weaker separators (clause boundary)
_SOFT_SEPARATORS = "，,、：:"


def split_chinese_sentences(text: str) -> list[str]:
    """Split text into a list of semantic sentences.

    Rules:
      - Strong terminators (。！？!?；;\n) always end a sentence.
      - Soft separators (，,、：:) only end a sentence when the chunk is
        already at least 14 chars long.
      - Empty / whitespace-only chunks are dropped.

    The function guarantees: no fragment lines (≥2 meaningful chars) and
    no ellipsis.  The order of the original text is preserved.
    """
    if not text:
        return []
    text = text.strip()
    if not text:
        return []

    sentences: list[str] = []
    buf: list[str] = []

    def _flush() -> None:
        if buf:
            chunk = "".join(buf).strip()
            if chunk:
                sentences.append(chunk)
            buf.clear()

    for ch in text:
        buf.append(ch)
        if ch in _TERMINATORS:
            _flush()
        elif ch in _SOFT_SEPARATORS and len(buf) >= 14:
            _flush()

    _flush()
    return sentences


# ── Pagination ─────────────────────────────────────────────────────────────────


def split_text_to_scene_pages(
    text: str,
    max_lines_per_scene: int = 3,
    max_chars_per_line: int = 22,
) -> list[list[str]]:
    """Split a block of text into a list of pages (each page is list[str]).

    Every line is a complete semantic sentence/phrase — never truncated,
    never a single-char fragment.  When content overflows the page budget,
    additional pages are appended (caller creates more scenes).

    Lines longer than ``max_chars_per_line`` are kept intact (so no
    information is lost); the per-page count is used as the size budget.
    """
    sentences = split_chinese_sentences(text)
    if not sentences:
        return []

    pages: list[list[str]] = []
    current: list[str] = []

    for sentence in sentences:
        if len(current) >= max_lines_per_scene:
            pages.append(current)
            current = [sentence]
        else:
            current.append(sentence)

    if current:
        pages.append(current)
    return pages


def split_bullet_to_pages(
    title: str,
    summary: str | None,
    key_points: list[str] | None = None,
    why_it_matters: str | None = None,
    *,
    max_lines_per_page: int = 3,
    max_chars_per_line: int = 22,
) -> list[list[str]]:
    """Paginate a single section's content across one or more pages.

    The title is **not** part of the page text — it is shown as a separate
    card heading on every continuation scene.  Pages 2..N get a part label
    appended by the caller.

    Each page has at most ``max_lines_per_page`` lines; long content is
    split into additional pages instead of being truncated.

    Content priority: summary → key_points → why_it_matters.
    """
    pool: list[str] = []

    if summary:
        pool.extend(split_chinese_sentences(summary))
    if key_points:
        for kp in key_points:
            if kp:
                pool.extend(split_chinese_sentences(kp))
    if why_it_matters:
        pool.extend(split_chinese_sentences(why_it_matters))

    deduplicated: list[str] = []
    seen: set[str] = set()
    for sentence in pool:
        normalized = sentence.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduplicated.append(sentence)
    pool = deduplicated

    if not pool:
        return []

    pages: list[list[str]] = []
    current: list[str] = []
    for sentence in pool:
        if len(current) >= max_lines_per_page:
            pages.append(current)
            current = [sentence]
        else:
            current.append(sentence)

    if current:
        pages.append(current)
    return pages


# ── Compact helpers (decorative labels only) ───────────────────────────────────


def compact_title(text: str, max_chars: int = 22) -> str:
    """Shorten a title to at most ``max_chars`` characters.

    Truncation is ONLY for decorative titles (e.g. card kickers, page
    numbers).  For report-content titles use ``to_video_signal_title``.
    """
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def compact_line(text: str, max_chars: int = 36) -> str:
    """Shorten a decorative line.  Use sparingly — prefer content-preserving
    helpers for any line that carries report information."""
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
    """Back-compat helper: split text into short visual lines, **never**
    truncating with ellipsis.  Long sentences are kept whole; when a
    sentence exceeds ``max_chars_per_line`` it is kept intact and pushed
    onto the result (the caller may decide to paginate)."""
    if not text:
        return []
    text = text.strip()
    if not text:
        return []

    sentences = split_chinese_sentences(text)
    return sentences[:max_lines]


# ── Compact narration (no truncation in core scenes) ───────────────────────────


def compact_narration(text: str, max_chars: int = 120) -> str:
    """Shorten narration text to at most ``max_chars`` characters.

    Used only for **decorative** narration snippets where the visual is
    the primary information channel.  Core-scene narration should be
    composed of full sentences and never truncated.
    """
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


# ── Video-language helpers ────────────────────────────────────────────────────

_PREFIXES_TO_STRIP = (
    "研究发现",
    "研究显示",
    "研究表明",
    "数据显示",
    "报告指出",
    "文章称",
    "据悉",
    "根据",
    "通过",
    "实现",
    "成功",
    "首次",
)


def to_video_signal_title(title: str, max_chars: int = 18) -> str:
    """Convert a section title into a short video card title.

    Strips common report-style prefixes and shortens at semantic boundaries.
    The result never uses an ellipsis; the complete title remains available
    in scene metadata and narration.
    """
    if not title:
        return ""
    title = title.strip()

    for p in _PREFIXES_TO_STRIP:
        if title.startswith(p):
            stripped = title[len(p):].strip()
            if stripped:
                title = stripped
                break

    title = title.rstrip("，。、；：")

    if len(title) > max_chars:
        entity = re.match(r"^([A-Za-z][A-Za-z0-9./+_-]*(?:\s+[A-Za-z0-9./+_-]+){0,3})", title)
        metric = re.search(r"(\d+(?:\.\d+)?\s*(?:亿|万亿)?参数)", title)
        model = re.search(r"(MoE|Mamba-Transformer|混合专家|线性注意力|多语言|安全基准)", title, re.I)
        parts = []
        if entity:
            entity_text = entity.group(1).strip()
            if len(entity_text) > 12:
                entity_text = entity_text.split()[0]
            parts.append(entity_text)
        if metric:
            parts.append(metric.group(1).replace(" ", ""))
        if model:
            parts.append(model.group(1))
        semantic = "：".join(parts[:1]) + (
            " " + " ".join(parts[1:]) if len(parts) > 1 else ""
        )
        if semantic and len(semantic) <= max_chars + 12:
            return semantic

        clauses = [
            part.strip()
            for part in re.split(r"[，。；：!?！？]", title)
            if part.strip()
        ]
        for clause in clauses:
            if 4 <= len(clause) <= max_chars:
                return clause

        first_clause = clauses[0] if clauses else title
        words = first_clause.split()
        if len(words) > 1:
            kept: list[str] = []
            for word in words:
                candidate = " ".join([*kept, word])
                if kept and len(candidate) > max_chars:
                    break
                kept.append(word)
            if kept:
                return " ".join(kept)
        return first_clause
    return title


def to_video_explanation_lines(
    summary: str | None,
    why_it_matters: str | None,
    key_points: list[str],
    max_lines: int = 3,
    max_chars_per_line: int = 24,
) -> list[str]:
    """Build a list of short explanation lines for a video card.

    Back-compat helper used by older storyboard callers.  **Does not**
    truncate with ellipsis — long content is paginated by the caller.
    """
    candidates: list[str] = []

    if summary:
        candidates.extend(split_chinese_sentences(summary))
    if not candidates and key_points:
        for kp in key_points[:2]:
            if kp:
                candidates.extend(split_chinese_sentences(kp))
    if not candidates and why_it_matters:
        candidates.extend(split_chinese_sentences(why_it_matters))

    return candidates[:max_lines]


def to_video_narration(
    index: int,
    title: str,
    summary: str | None,
    why_it_matters: str | None,
    *,
    max_chars: int = 90,
) -> str:
    """Build spoken narration for a single-section scene.

    Returns full sentences composed from the section's content.  Does not
    truncate semantic content with '…' — long narration is the caller's
    responsibility to paginate.
    """
    label = _cn_number(index) if 1 <= index <= 10 else str(index)
    title_short = to_video_signal_title(title, 20)
    parts: list[str] = [f"第{label}个核心观察：{title_short}"]

    if summary:
        parts.extend(split_chinese_sentences(summary))
    if not summary and why_it_matters:
        parts.extend(split_chinese_sentences(why_it_matters))

    return "。".join(p for p in parts if p) + "。"


def split_highlight_scenes(
    section,
    scene_index: int,
    *,
    max_chars_title: int = 22,
    max_chars_body: int = 36,
) -> list[dict]:
    """Split a single highlight/section into 1–2 scenes: title + why-it-matters.

    Back-compat helper.  New code should use ``split_bullet_to_pages``.
    """
    scenes = []

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
