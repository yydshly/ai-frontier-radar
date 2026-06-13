"""content_video — Storyboard builder.

Converts a VideoSourceSnapshot into a list of VideoScene objects.

Scene breakdown (V1 — short-form, mobile-first)
───────────────────────────────────────────────
1. Cover        — brand + date + "N 个重点信号" (no long title)
2. Overall      — today's core judgment (brief)
3..N           — per highlight (max 3), split into:
                   A. Signal title page (信号 N)
                   B. Why important page (为什么重要)
N+1             — Today's conclusion (今日结论) — compressed
N+2             — Ending / CTA
"""
from __future__ import annotations

from app.application.content_video.models import VideoSourceSnapshot, VideoScene
from app.application.content_video.text_utils import (
    compact_title,
    compact_line,
    split_to_visual_lines,
    compact_narration,
    split_highlight_scenes,
)


def _cn_number(n: int) -> str:
    """Convert int to Chinese number word (1-10)."""
    if n == 1:
        return "一"
    if n == 2:
        return "二"
    if n == 3:
        return "三"
    if n == 4:
        return "四"
    if n == 5:
        return "五"
    if n == 6:
        return "六"
    if n == 7:
        return "七"
    if n == 8:
        return "八"
    if n == 9:
        return "九"
    if n == 10:
        return "十"
    return str(n)


def _clean_text(text: str, max_chars: int = 200) -> str:
    """Trim whitespace and cap length for narration."""
    text = text.strip()
    if len(text) > max_chars:
        text = text[: max_chars - 3] + "..."
    return text


def _build_narration_for_highlight(idx: int, section, *, prefix: str = "") -> str:
    """Build narration text for a highlight scene."""
    label = _cn_number(idx)
    parts = []
    if prefix:
        parts.append(prefix)
    else:
        parts.append(f"第{label}个值得关注的信号是：{compact_title(section.title, 22)}。")
    if section.summary:
        parts.append(compact_narration(section.summary, 100))
    if section.why_it_matters:
        parts.append(f"这值得关注，因为{compact_narration(section.why_it_matters, 100)}。")
    return "".join(parts)


def build_storyboard(snapshot: VideoSourceSnapshot) -> list[VideoScene]:
    """Split a VideoSourceSnapshot into a list of VideoScene objects.

    V1 short-form template (mobile-first):
      1. Cover          — brand, date, N signals count (no long title)
      2. Overall        — today's core judgment (brief)
      3..N             — per highlight (max 3):
                           A. Signal title page
                           B. Why important page (split from same section)
      N+1               — Today's conclusion (compressed takeaways)
      N+2               — Ending
    """
    scenes: list[VideoScene] = []
    scene_index = 1

    # ── Scene 1: Cover ────────────────────────────────────────────────────
    # Simplified cover: brand + date + signal count, NOT long title
    signal_count = len(snapshot.sections[:3])
    count_label = _cn_number(signal_count) if signal_count <= 10 else str(signal_count)
    cover_lines = [
        snapshot.date_label or "",
        f"{count_label} 个重点信号",
    ]
    is_radar = snapshot.source_key.startswith("radar_")
    cover_narration = (
        "这里是今日 AI 前沿雷达，为你整理今天最值得关注的前沿信号。"
        if is_radar
        else f"这里是本期内容简报，为你整理重点信息。日期：{snapshot.date_label or ''}。"
    )

    scenes.append(
        VideoScene(
            scene_id=f"scene_{scene_index:02d}",
            scene_type="cover",
            visual_title="AI 前沿雷达",
            visual_lines=cover_lines,
            narration_text=cover_narration,
            source_label=snapshot.date_label,
        )
    )
    scene_index += 1

    # ── Scene 2: Overall judgment ───────────────────────────────────────
    if snapshot.summary:
        summary_short = compact_narration(snapshot.summary, 120)
        summary_lines = split_to_visual_lines(
            snapshot.summary, max_lines=2, max_chars_per_line=28
        )
        scenes.append(
            VideoScene(
                scene_id=f"scene_{scene_index:02d}",
                scene_type="summary",
                visual_title="今日总判断",
                visual_lines=summary_lines[:2],
                narration_text=summary_short,
            )
        )
        scene_index += 1

    # ── Scenes 3..N: Highlights (max 3, each may produce 1–2 scenes) ─────
    max_highlights = 3
    selected_sections = snapshot.sections[:max_highlights]

    for idx, section in enumerate(selected_sections, start=1):
        # Split each highlight into up to 2 scenes: title + detail
        highlight_scenes = split_highlight_scenes(
            section,
            scene_index,
            max_chars_title=22,
            max_chars_body=36,
        )

        for hs in highlight_scenes:
            # Build narration: prefix + section content
            if hs["scene_type"] == "highlight":
                # Signal title page: use prefix + title + summary
                summary_short = compact_narration(section.summary, 80) if section.summary else ""
                narration = (
                    f"第{_cn_number(idx)}个值得关注的信号是："
                    f"{compact_title(section.title, 22)}。"
                    + (f" {summary_short}" if summary_short else "")
                )
                visual_lines = hs["visual_lines"]
                scenes.append(
                    VideoScene(
                        scene_id=f"scene_{scene_index:02d}",
                        scene_type="highlight",
                        visual_title=compact_title(section.title, 22),
                        visual_lines=visual_lines,
                        narration_text=compact_narration(narration, 120),
                        source_label=section.source_name,
                    )
                )
            else:
                # Why important page: use why_it_matters or key_points
                narration_prefix = hs.get("narration_prefix", "")
                if section.why_it_matters:
                    why_text = compact_narration(section.why_it_matters, 100)
                elif section.key_points:
                    why_text = compact_narration(section.key_points[0], 80)
                else:
                    why_text = ""
                narration = compact_narration(narration_prefix + why_text, 120)
                scenes.append(
                    VideoScene(
                        scene_id=f"scene_{scene_index:02d}",
                        scene_type="highlight_detail",
                        visual_title="为什么重要",
                        visual_lines=hs["visual_lines"],
                        narration_text=narration,
                        source_label=section.source_name,
                    )
                )
            scene_index += 1

    # ── Takeaways / Conclusion ───────────────────────────────────────────
    if snapshot.takeaways:
        # Compress each takeaway to ≤28 chars
        compressed: list[str] = []
        for t in snapshot.takeaways[:5]:
            line = compact_line(t, max_chars=28)
            if line:
                compressed.append(line)

        if compressed:
            takeaway_lines = [f"{idx}. {t}" for idx, t in enumerate(compressed, start=1)]
            takeaway_narration = compact_narration(
                "总结来看，今天最值得记住的是："
                + "；".join(compressed),
                120,
            )
            scenes.append(
                VideoScene(
                    scene_id=f"scene_{scene_index:02d}",
                    scene_type="takeaways",
                    visual_title="今日结论",
                    visual_lines=takeaway_lines[:4],  # max 4 lines
                    narration_text=takeaway_narration,
                )
            )
            scene_index += 1

    # ── Last: Ending ──────────────────────────────────────────────────────
    scenes.append(
        VideoScene(
            scene_id=f"scene_{scene_index:02d}",
            scene_type="ending",
            visual_title="查看完整报告",
            visual_lines=[
                "扫码查看完整报告",
                "语音播报 · 全部文章原文",
            ],
            narration_text="以上是本期简报。你可以在分享页查看完整报告和原始来源。",
        )
    )

    return scenes
