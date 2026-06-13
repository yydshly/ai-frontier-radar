"""content_video — Storyboard builder.

Converts a VideoSourceSnapshot into a list of VideoScene objects.

Scene breakdown (V1.5 — storyboard-first, image quality priority)
─────────────────────────────────────────────────────────────────
1. opening_summary  — brand + date + 3 signal chips
2. summary_overview — numbered 01/02/03 core judgments
3..N               — signal (1 per highlight, max 3)
N+1                — supporting_notes (compressed secondary observations)
N+2                — closing_cta (QR + CTA)
"""
from __future__ import annotations

from app.application.content_video.models import VideoSourceSnapshot, VideoScene
from app.application.content_video.text_utils import (
    compact_line,
    split_to_visual_lines,
    compact_narration,
    to_video_signal_title,
    to_video_explanation_lines,
    to_video_narration,
)
from app.application.content_video.settings import (
    get_max_highlights,
    get_max_narration_chars,
)


def _cn_number(n: int) -> str:
    if n == 1: return "一"
    if n == 2: return "二"
    if n == 3: return "三"
    if n == 4: return "四"
    if n == 5: return "五"
    if n == 6: return "六"
    if n == 7: return "七"
    if n == 8: return "八"
    if n == 9: return "九"
    if n == 10: return "十"
    return str(n)


def _clean_text(text: str, max_chars: int = 200) -> str:
    text = text.strip()
    if len(text) > max_chars:
        text = text[: max_chars - 3] + "..."
    return text


def build_storyboard(snapshot: VideoSourceSnapshot) -> list[VideoScene]:
    """Split a VideoSourceSnapshot into a list of VideoScene objects.

    V1.5 storyboard-first template:
      1. opening_summary  — brand, date, top-3 signal titles as chips
      2. summary_overview — numbered 01/02/03 core judgments
      3..N              — signal (1 per signal, with signal_index metadata)
      N+1               — supporting_notes
      N+2               — closing_cta
    """
    scenes: list[VideoScene] = []
    scene_index = 1
    max_highlights = get_max_highlights()
    max_narration_chars = get_max_narration_chars()
    is_radar = snapshot.source_key.startswith("radar_")

    # ── Scene 1: Opening Summary ─────────────────────────────────────────
    top_signals = snapshot.sections[:max_highlights]
    chip_lines = [to_video_signal_title(s.title, max_chars=16) for s in top_signals[:3]]

    opening_narration = (
        "这里是今日 AI 前沿雷达，为你整理今天最值得关注的前沿信号。"
        if is_radar
        else f"这里是本期内容简报，为你整理重点信息。日期：{snapshot.date_label or ''}。"
    )
    scenes.append(
        VideoScene(
            scene_id=f"scene_{scene_index:02d}",
            scene_type="opening_summary",
            visual_title="今日 AI 前沿简报",
            visual_lines=chip_lines,
            narration_text=compact_narration(opening_narration, max_narration_chars),
            source_label=snapshot.date_label,
            metadata={"top_signal_titles": [s.title for s in top_signals[:3]]},
        )
    )
    scene_index += 1

    # ── Scene 2: Summary Overview ─────────────────────────────────────────
    if snapshot.summary:
        summary_lines = split_to_visual_lines(
            snapshot.summary, max_lines=3, max_chars_per_line=22,
        )
        summary_narration = compact_narration(
            "今天的核心判断是：" + _clean_text(snapshot.summary, 80),
            max_chars=max_narration_chars,
        )
        scenes.append(
            VideoScene(
                scene_id=f"scene_{scene_index:02d}",
                scene_type="summary_overview",
                visual_title="今日最值得关注",
                visual_lines=summary_lines[:3],
                narration_text=summary_narration,
            )
        )
        scene_index += 1

    # ── Scenes 3..N: Signals ──────────────────────────────────────────────
    for signal_idx, section in enumerate(top_signals):
        signal_title = to_video_signal_title(section.title, max_chars=18)
        explanation_lines = to_video_explanation_lines(
            summary=section.summary,
            why_it_matters=section.why_it_matters,
            key_points=section.key_points or [],
            max_lines=3,
            max_chars_per_line=22,
        )
        narration = to_video_narration(
            index=signal_idx + 1,
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
                metadata={"signal_index": signal_idx},
            )
        )
        scene_index += 1

    # ── Supporting Notes ────────────────────────────────────────────────
    if snapshot.takeaways:
        compressed: list[str] = []
        for t in snapshot.takeaways[:4]:
            line = compact_line(t, max_chars=28)
            if line:
                compressed.append(line)
        if compressed:
            supporting_narration = compact_narration(
                "此外，今天还有：" + "；".join(compressed[:4]),
                max_chars=max_narration_chars,
            )
            scenes.append(
                VideoScene(
                    scene_id=f"scene_{scene_index:02d}",
                    scene_type="supporting_notes",
                    visual_title="补充观察",
                    visual_lines=compressed[:4],
                    narration_text=supporting_narration,
                )
            )
            scene_index += 1

    # ── Closing CTA ──────────────────────────────────────────────────────
    scenes.append(
        VideoScene(
            scene_id=f"scene_{scene_index:02d}",
            scene_type="closing_cta",
            visual_title="查看完整报告",
            visual_lines=[
                "扫码查看完整报告",
                "语音播报 · 全部文章原文",
            ],
            narration_text="以上是本期简报。你可以在分享页查看完整报告和原始来源。",
            source_label=snapshot.date_label,
        )
    )

    return scenes
