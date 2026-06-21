"""content_video — Storyboard builder for full-report share videos.

The storyboard turns a ``VideoSourceSnapshot`` into a list of
``VideoScene`` objects that the renderer / TTS pipeline consumes.

Scene breakdown (V2 — full-report briefing)
────────────────────────────────────────────
1.  opening              — brand + date + full report title +
                           "本报告包含 N 个核心观察" + "接下来按顺序展开"
2..N  overview_paged     — overview split by Chinese punctuation into
                           pages of 2–4 full sentences each.  No ellipsis.
N+1..M core_insight      — one scene per section; long sections split
                           into core_insight_continuation scenes.
M+1..P supporting        — takeaways paginated 2–4 items each.
P+1   closing            — report summary + shareUrl / qrCodeDataUrl.

Design principles
─────────────────
* Core content is never truncated.  Long content creates more scenes.
* visual_title / visual_lines / narration_text share the same source
  text — visual & audio are in sync.
* Decoration-only labels may be shortened; report content must not.
* The number of scenes is bounded by ``get_max_scenes()``; when the
  budget is exhausted we still cover the FIRST N sections and ALL of
  the overview + takeaways, because the overview and bullets carry
  more weight than the tail sections.
"""
from __future__ import annotations

import re

from app.application.content_video.models import VideoScene, VideoSourceSnapshot, VideoSourceSection
from app.application.content_video.text_utils import (
    contains_ellipsis,
    is_fragment_line,
    remove_ellipsis,
    split_bullet_to_pages,
    split_chinese_sentences,
    split_text_to_scene_pages,
    to_video_signal_title,
)
from app.application.content_video.settings import (
    get_max_narration_chars,
    get_max_scenes,
)


# ── Page-size tunables ────────────────────────────────────────────────────────

# Overview pages: each page shows 2–4 sentences.
OVERVIEW_MAX_LINES_PER_PAGE = 3
OVERVIEW_MAX_CHARS_PER_LINE = 28

# Per-section bullet pages: each page shows 2–3 sentences.
SECTION_MAX_LINES_PER_PAGE = 3
SECTION_MAX_CHARS_PER_LINE = 28

# Supporting notes pages: 2–4 items per page.
SUPPORTING_MAX_LINES_PER_PAGE = 3
SUPPORTING_MAX_CHARS_PER_LINE = 28

# Narration characters per scene.  This is a SOFT cap — we never truncate
# core narration with '…'; instead we paginate by reducing scene-level
# pages.
DEFAULT_NARRATION_CHARS = 240


# ── Helpers ───────────────────────────────────────────────────────────────────


def _safe_title(title: str, *, max_chars: int = 30) -> str:
    """Return a non-truncated, non-fragment title for a section.

    The short decorative title for video cards still uses
    ``to_video_signal_title``; this helper is for the FULL title shown on
    the opening / closing scenes where space permits."""
    if not title:
        return ""
    cleaned = title.strip()
    cleaned = remove_ellipsis(cleaned)
    return cleaned


def _make_continuation_kicker(index_label: str, part: int | None) -> str:
    if part is None or part <= 1:
        return f"CORE INSIGHT {index_label}"
    return f"CORE INSIGHT {index_label} · PART {part}"


def _format_overview_kicker(page_idx: int, total_pages: int) -> str:
    if total_pages <= 1:
        return "TODAY'S OVERVIEW"
    return f"TODAY'S OVERVIEW · {page_idx + 1}/{total_pages}"


def _format_supporting_kicker(page_idx: int, total_pages: int) -> str:
    if total_pages <= 1:
        return "MORE SIGNALS"
    return f"MORE SIGNALS · {page_idx + 1}/{total_pages}"


def _build_pages_for_section(
    section: VideoSourceSection,
    *,
    max_lines_per_page: int = SECTION_MAX_LINES_PER_PAGE,
    max_chars_per_line: int = SECTION_MAX_CHARS_PER_LINE,
) -> list[list[str]]:
    """Return a list of pages for a single section's content.

    Uses summary → key_points → why_it_matters as the content pool."""
    pages = split_bullet_to_pages(
        section.title,
        section.summary,
        section.key_points or [],
        section.why_it_matters,
        max_lines_per_page=max_lines_per_page,
        max_chars_per_line=max_chars_per_line,
    )
    # Fallback when the section has only a title (defensive)
    if not pages and section.title:
        pages = [[section.title]]
    return pages


# ── Scene factories ───────────────────────────────────────────────────────────


def _build_opening_scene(
    snapshot: VideoSourceSnapshot,
    scene_index: int,
) -> VideoScene:
    """Scene 1: opening.  Brand + date + full report title + core count."""
    section_count = len(snapshot.sections)
    is_radar = snapshot.source_key.startswith("radar_")

    title = _safe_title(snapshot.title or "AI 前沿雷达", max_chars=40)
    brand = "AI FRONTIER RADAR"
    date = snapshot.date_label or ""

    # Use complete sentences; never truncate.
    visual_lines: list[str] = []

    narration_parts: list[str] = [
        f"{brand}，{date}。",
        f"本期主题：{title}。",
    ]
    if section_count > 0:
        section_word = "个" if is_radar else "个"
        if is_radar:
            narration_parts.append(
                f"本期共包含 {section_count} {section_word}核心观察，接下来按顺序展开。"
            )
            visual_lines.append(
                f"本期包含 {section_count} 个核心观察"
            )
        else:
            narration_parts.append(
                f"本期共包含 {section_count} {section_word}核心观察。"
            )
            visual_lines.append(
                f"本期包含 {section_count} 个核心观察"
            )
        narration_parts.append("以下是核心内容。")
    else:
        narration_parts.append("以下是核心内容。")
    visual_lines.append("接下来按顺序展开")

    return VideoScene(
        scene_id=f"scene_{scene_index:02d}",
        scene_type="opening",
        visual_title="AI 前沿雷达 · 入口",
        visual_lines=visual_lines,
        narration_text="".join(narration_parts),
        source_label=date,
        metadata={"brand": brand, "section_count": section_count},
    )


def _build_overview_scenes(
    snapshot: VideoSourceSnapshot,
    *,
    start_index: int,
    max_total_scenes: int | None = None,
) -> tuple[list[VideoScene], int]:
    """Paginate ``snapshot.summary`` into one or more ``overview_paged`` scenes.

    The caller is responsible for providing ``max_total_scenes`` (an upper
    bound on the resulting scene count).  When the overview would exceed
    the budget, we keep only the FIRST pages so the opening + closing
    scenes can still be created.
    """
    scenes: list[VideoScene] = []
    if not snapshot.summary:
        return scenes, start_index

    pages = split_text_to_scene_pages(
        snapshot.summary,
        max_lines_per_scene=OVERVIEW_MAX_LINES_PER_PAGE,
        max_chars_per_line=OVERVIEW_MAX_CHARS_PER_LINE,
    )
    if not pages:
        return scenes, start_index

    # Defensive: if max_total_scenes is set, reserve at least 1 scene for
    # closing and (optionally) for sections.  We don't strictly enforce
    # this here — the caller decides.  We just keep ALL pages of the
    # overview because the overview carries the highest signal density.
    total_pages = len(pages)
    idx = start_index
    for page_idx, page in enumerate(pages):
        kicker = _format_overview_kicker(page_idx, total_pages)
        narration = "今天的整体判断是：" + "，".join(page) + "。"
        scenes.append(
            VideoScene(
                scene_id=f"scene_{idx:02d}",
                scene_type="overview_paged",
                visual_title="今日整体判断",
                visual_lines=page,
                narration_text=narration,
                metadata={"page": page_idx + 1, "total_pages": total_pages, "kicker": kicker},
            )
        )
        idx += 1
    return scenes, idx


def _build_core_insight_scenes(
    snapshot: VideoSourceSnapshot,
    *,
    start_index: int,
    max_total_scenes: int | None = None,
) -> tuple[list[VideoScene], int, int]:
    """Create one or more scenes for every section in ``snapshot.sections``.

    Returns (scenes, next_index, sections_covered_count).

    Budget handling: when ``max_total_scenes`` is set and we are about to
    exceed it, we stop adding NEW sections but still finish the current
    section (its pages go through).  Section index labels stay
    consistent (only sections actually covered get a number).
    """
    scenes: list[VideoScene] = []
    if not snapshot.sections:
        return scenes, start_index, 0

    idx = start_index
    sections_covered = 0

    for section_idx, section in enumerate(snapshot.sections, start=1):
        # Reserve at least 1 scene for closing.
        if max_total_scenes is not None and idx >= max_total_scenes - 1:
            break

        pages = _build_pages_for_section(section)
        if not pages:
            continue

        sections_covered += 1
        index_label = f"{section_idx:02d}"

        short_title = to_video_signal_title(section.title, max_chars=24)
        full_title = _safe_title(section.title, max_chars=60)

        for page_idx, page in enumerate(pages):
            part = page_idx + 1
            kicker = _make_continuation_kicker(index_label, part)

            scene_title = short_title if part == 1 else f"{short_title}（续）"

            # Compose narration from this page's lines. The page text already
            # contains the section's content, so we do NOT also read section.title
            # (it equals the body for radar highlights) — that would say each
            # point twice. We only add a short ordinal lead-in on the first page.
            page_text = "".join(f"{ln}。" for ln in page)
            if part == 1:
                narration = f"第{_cn_number(section_idx)}个核心观察。{page_text}"
            else:
                narration = f"接着看。{page_text}"

            scenes.append(
                VideoScene(
                    scene_id=f"scene_{idx:02d}",
                    scene_type="core_insight" if part == 1 else "core_insight_continuation",
                    visual_title=scene_title,
                    visual_lines=page,
                    narration_text=narration,
                    source_label=section.source_name or snapshot.date_label,
                    metadata={
                        "section_index": section_idx,
                        "part": part,
                        "total_parts": len(pages),
                        "kicker": kicker,
                        "section_title": section.title,
                        "short_title": short_title,
                        "full_title": full_title,
                    },
                )
            )
            idx += 1

            if max_total_scenes is not None and idx >= max_total_scenes - 1:
                break
        if max_total_scenes is not None and idx >= max_total_scenes - 1:
            break

    return scenes, idx, sections_covered


def _build_supporting_scenes(
    snapshot: VideoSourceSnapshot,
    *,
    start_index: int,
    max_total_scenes: int | None = None,
) -> tuple[list[VideoScene], int]:
    """Paginate ``snapshot.takeaways`` into supporting-notes scenes.

    No truncation — every takeaway is rendered somewhere in the video,
    even if it costs extra scenes.
    """
    scenes: list[VideoScene] = []
    if not snapshot.takeaways:
        return scenes, start_index

    # Build sentences from each takeaway so we don't fragment mid-clause.
    sentences: list[str] = []
    for t in snapshot.takeaways:
        if not t:
            continue
        sentences.extend(split_chinese_sentences(t))
    if not sentences:
        return scenes, start_index

    pages: list[list[str]] = []
    current: list[str] = []
    for sent in sentences:
        if len(current) >= SUPPORTING_MAX_LINES_PER_PAGE:
            pages.append(current)
            current = [sent]
        else:
            current.append(sent)
    if current:
        pages.append(current)

    total_pages = len(pages)
    idx = start_index
    for page_idx, page in enumerate(pages):
        if max_total_scenes is not None and idx >= max_total_scenes - 1:
            break
        kicker = _format_supporting_kicker(page_idx, total_pages)
        narration = "补充观察：" + "，".join(page) + "。"
        scenes.append(
            VideoScene(
                scene_id=f"scene_{idx:02d}",
                scene_type="supporting_notes",
                visual_title="补充观察",
                visual_lines=page,
                narration_text=narration,
                metadata={"page": page_idx + 1, "total_pages": total_pages, "kicker": kicker},
            )
        )
        idx += 1
    return scenes, idx


def _build_closing_scene(
    snapshot: VideoSourceSnapshot,
    scene_index: int,
    *,
    sections_covered: int,
    share_url: str | None = None,
    qr_code_data_url: str | None = None,
    summary_lines: list[str] | None = None,
) -> VideoScene:
    """Build the closing scene with report summary + shareUrl / QR."""
    visual_lines: list[str] = list(summary_lines or [])
    narration_parts: list[str] = []

    if sections_covered > 0:
        visual_lines.append(f"本期共播报 {sections_covered} 个核心观察")
        narration_parts.append(f"以上是本期 {sections_covered} 个核心观察。")

    if qr_code_data_url:
        visual_lines.append("扫码查看完整报告")
        narration_parts.append("扫描屏幕上的二维码查看完整报告。")
    else:
        visual_lines.append("通过下方链接查看完整报告")
        narration_parts.append("通过屏幕上的链接查看完整报告。")
    if share_url:
        visual_lines.append(f"或访问：{share_url}")
        narration_parts.append(f"或访问链接：{share_url}。")

    # Make sure visual_lines has at least something useful.
    if not visual_lines:
        visual_lines = ["本期结束", "查看完整报告"]

    return VideoScene(
        scene_id=f"scene_{scene_index:02d}",
        scene_type="closing",
        visual_title="查看完整报告",
        visual_lines=visual_lines,
        narration_text="".join(narration_parts) or "本期结束。请扫码查看完整报告。",
        source_label=snapshot.date_label,
        metadata={
            "share_url": share_url,
            "qr_code_data_url": qr_code_data_url,
            "sections_covered": sections_covered,
        },
    )


# ── Small helpers used by the storyboard ──────────────────────────────────────


def _cn_number(n: int) -> str:
    digits = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    if 1 <= n <= 10:
        return digits[n]
    return str(n)


# ── Main entry point ──────────────────────────────────────────────────────────


def build_storyboard(
    snapshot: VideoSourceSnapshot,
    *,
    share_url: str | None = None,
    qr_code_data_url: str | None = None,
) -> list[VideoScene]:
    """Build the full-report storyboard.

    Priority for the scene budget (when we hit the cap):
      1. Opening (always)
      2. ALL core sections — each gets at least one scene
      3. Closing (always)
      4. Overview pagination
      5. Supporting notes pagination

    This guarantees that the user can hear/see every bullet regardless
    of total budget pressure.  Overview and supporting notes can be
    trimmed when the budget is exhausted.
    """
    scenes: list[VideoScene] = []
    scene_index = 1

    # ── 1. Opening ────────────────────────────────────────────────────────
    scenes.append(_build_opening_scene(snapshot, scene_index))
    scene_index += 1

    # ── 2. Overview ──────────────────────────────────────────────────────
    overview_scenes, scene_index = _build_overview_scenes(
        snapshot,
        start_index=scene_index,
    )
    scenes.extend(overview_scenes)

    # ── 3. Core sections ─────────────────────────────────────────────────
    core_scenes, scene_index, sections_covered = _build_core_insight_scenes(
        snapshot,
        start_index=scene_index,
    )
    scenes.extend(core_scenes)

    # ── 4. Supporting notes ──────────────────────────────────────────────
    supporting_scenes, scene_index = _build_supporting_scenes(
        snapshot,
        start_index=scene_index,
    )
    scenes.extend(supporting_scenes)

    # ── 5. Closing ────────────────────────────────────────────────────────
    summary_lines: list[str] = []
    if snapshot.summary:
        summary_lines.extend(
            split_chinese_sentences(snapshot.summary)[:2]
        )
    if not summary_lines:
        summary_lines = [
            s.title for s in snapshot.sections[:3] if s.title
        ]

    scenes.append(
        _build_closing_scene(
            snapshot,
            scene_index,
            sections_covered=sections_covered,
            share_url=share_url,
            qr_code_data_url=qr_code_data_url,
            summary_lines=summary_lines,
        )
    )

    # ── Defensive: ensure no scene contains ellipsis or fragment lines ──
    for sc in scenes:
        sc.visual_title = remove_ellipsis(sc.visual_title)
        sc.visual_lines = [remove_ellipsis(ln) for ln in sc.visual_lines]
        sc.narration_text = remove_ellipsis(sc.narration_text)
        sc.visual_lines = [
            ln for ln in sc.visual_lines if not is_fragment_line(ln)
        ]

    return scenes
