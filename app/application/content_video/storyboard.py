"""content_video — Storyboard builder.

Converts a VideoSourceSnapshot into a list of VideoScene objects.

Scene breakdown (V1 — fixed template)
──────────────────────────────────────
1. Cover      — title, date, subtitle
2. Core       — snapshot.summary
3..N          — snapshot.sections (first 3–5), one scene per section
N+1           — Takeaways
N+2           — Ending / CTA
"""
from __future__ import annotations

from app.application.content_video.models import VideoSourceSnapshot, VideoScene


def _cn_number(n: int) -> str:
    """Convert int to Chinese number word."""
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
    return str(n)


def _clean_text(text: str, max_chars: int = 200) -> str:
    """Trim whitespace and cap length for narration."""
    text = text.strip()
    if len(text) > max_chars:
        text = text[: max_chars - 3] + "..."
    return text


def _build_narration_for_section(index: int, section, total: int) -> str:
    """Build narration text for a section scene."""
    label = _cn_number(index)
    narration = f"第{label}个重点是：{_clean_text(section.title, 100)}。"
    if section.summary:
        narration += f" {_clean_text(section.summary, 150)}。"
    if section.why_it_matters:
        narration += f"这值得关注，因为 {_clean_text(section.why_it_matters, 100)}。"
    return narration


def build_storyboard(snapshot: VideoSourceSnapshot) -> list[VideoScene]:
    """Split a VideoSourceSnapshot into a list of VideoScene objects.

    V1 uses a fixed template:
      1. Cover
      2. Core summary
      3..N  Sections (max 5)
      N+1   Takeaways (if any)
      N+2   Ending
    """
    scenes: list[VideoScene] = []
    scene_index = 1

    # ── Scene 1: Cover ────────────────────────────────────────────────────
    cover_lines = [snapshot.title]
    if snapshot.subtitle:
        cover_lines.append(snapshot.subtitle)
    if snapshot.date_label:
        cover_lines.append(snapshot.date_label)

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
            visual_title=snapshot.title,
            visual_lines=cover_lines,
            narration_text=cover_narration,
            source_label=snapshot.date_label,
        )
    )
    scene_index += 1

    # ── Scene 2: Core Summary ─────────────────────────────────────────────
    if snapshot.summary:
        summary_narration = _clean_text(snapshot.summary, 300)
        scenes.append(
            VideoScene(
                scene_id=f"scene_{scene_index:02d}",
                scene_type="summary",
                visual_title="核心判断",
                visual_lines=[
                    _clean_text(snapshot.summary, 120),
                    _clean_text(snapshot.subtitle or "", 120),
                ],
                narration_text=summary_narration,
            )
        )
        scene_index += 1

    # ── Scenes 3..N: Sections ────────────────────────────────────────────
    max_sections = 5
    selected_sections = snapshot.sections[:max_sections]
    for idx, section in enumerate(selected_sections, start=1):
        visual_lines = [section.title]
        if section.summary:
            visual_lines.append(_clean_text(section.summary, 120))
        if section.key_points:
            for kp in section.key_points[:3]:
                visual_lines.append(f"• {kp}")
        narration = _build_narration_for_section(idx, section, len(selected_sections))
        scenes.append(
            VideoScene(
                scene_id=f"scene_{scene_index:02d}",
                scene_type="highlight",
                visual_title=section.title,
                visual_lines=visual_lines,
                narration_text=narration,
                source_label=section.source_name,
            )
        )
        scene_index += 1

    # ── Second-to-last: Takeaways ─────────────────────────────────────────
    if snapshot.takeaways:
        takeaway_lines = [f"{idx}. {t}" for idx, t in enumerate(snapshot.takeaways[:5], start=1)]
        takeaway_narration = "总结来看，今天最值得记住的是：" + "；".join(
            snapshot.takeaways[:5]
        ) + "。"
        scenes.append(
            VideoScene(
                scene_id=f"scene_{scene_index:02d}",
                scene_type="takeaways",
                visual_title="今日值得记住",
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
                snapshot.title,
                snapshot.date_label or "",
                "扫码查看完整报告",
            ],
            narration_text="以上是本期简报。你可以在分享页查看完整报告和原始来源。",
        )
    )

    return scenes
