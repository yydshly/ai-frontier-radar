"""content_video — Storyboard builder.

Converts a VideoSourceSnapshot into a list of VideoScene objects.

Scene breakdown (V1.1 — mobile briefing, ~60s)
─────────────────────────────────────────────
1. Cover        — brand + date + signal count
2. Summary      — today's core judgment (brief)
3..N           — per highlight/signal (max 3), ONE scene each:
                   visual_title = short signal name
                   visual_lines = 1-2 punchy explanation lines
                   narration_text = spoken narration (~90 chars)
N+1             — Takeaways (compressed)
N+2             — Ending / CTA
"""
from __future__ import annotations

from app.application.content_video.models import VideoSourceSnapshot, VideoScene
from app.application.content_video.text_utils import (
    compact_title,
    compact_line,
    split_to_visual_lines,
    compact_narration,
    to_video_signal_title,
    to_video_explanation_lines,
    to_video_narration,
)
from app.application.content_video.settings import (
    get_max_scenes,
    get_max_highlights,
    get_max_narration_chars,
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


def build_storyboard(snapshot: VideoSourceSnapshot) -> list[VideoScene]:
    """Split a VideoSourceSnapshot into a list of VideoScene objects.

    V1.1 mobile briefing template:
      1. Cover          — brand, date, signal count (no long title)
      2. Summary       — today's core judgment (brief)
      3..N            — per highlight (max 3, from settings):
                           ONE scene per signal (title + explanation lines)
      N+1              — Takeaways (compressed)
      N+2              — Ending
    """
    scenes: list[VideoScene] = []
    scene_index = 1
    max_highlights = get_max_highlights()
    max_narration_chars = get_max_narration_chars()

    # ── Scene 1: Cover ────────────────────────────────────────────────────
    signal_count = len(snapshot.sections[:max_highlights])
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
            narration_text=compact_narration(cover_narration, max_narration_chars),
            source_label=snapshot.date_label,
        )
    )
    scene_index += 1

    # ── Scene 2: Overall summary ──────────────────────────────────────────
    if snapshot.summary:
        summary_lines = split_to_visual_lines(
            snapshot.summary,
            max_lines=3,
            max_chars_per_line=24,
        )
        summary_narration = compact_narration(
            "今天的核心判断是：" + _clean_text(snapshot.summary, 80),
            max_chars=max_narration_chars,
        )
        scenes.append(
            VideoScene(
                scene_id=f"scene_{scene_index:02d}",
                scene_type="summary",
                visual_title="今日总判断",
                visual_lines=summary_lines[:3],
                narration_text=summary_narration,
            )
        )
        scene_index += 1

    # ── Scenes 3..N: Signals (1 scene each) ──────────────────────────────
    selected_sections = snapshot.sections[:max_highlights]

    for idx, section in enumerate(selected_sections, start=1):
        # Video-language title: short and punchy
        signal_title = to_video_signal_title(section.title, max_chars=18)
        # Explanation lines: why it matters condensed into 1-3 short lines
        explanation_lines = to_video_explanation_lines(
            summary=section.summary,
            why_it_matters=section.why_it_matters,
            key_points=section.key_points or [],
            max_lines=3,
            max_chars_per_line=24,
        )
        # Spoken narration
        narration = to_video_narration(
            index=idx,
            title=section.title,
            summary=section.summary,
            why_it_matters=section.why_it_matters,
            max_chars=max_narration_chars,
        )

        scenes.append(
            VideoScene(
                scene_id=f"scene_{scene_index:02d}",
                scene_type="signal",
                visual_title=signal_title,
                visual_lines=explanation_lines[:3],
                narration_text=narration,
                source_label=section.source_name,
            )
        )
        scene_index += 1

    # ── Takeaways / Conclusion ───────────────────────────────────────────
    if snapshot.takeaways:
        compressed: list[str] = []
        for t in snapshot.takeaways[:5]:
            line = compact_line(t, max_chars=26)
            if line:
                compressed.append(line)

        if compressed:
            takeaway_lines = [f"{idx}. {t}" for idx, t in enumerate(compressed[:4], start=1)]
            takeaway_narration = compact_narration(
                "总结来看，今天最值得记住的是：" + "；".join(compressed[:4]),
                max_chars=max_narration_chars,
            )
            scenes.append(
                VideoScene(
                    scene_id=f"scene_{scene_index:02d}",
                    scene_type="takeaways",
                    visual_title="今日结论",
                    visual_lines=takeaway_lines,
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
