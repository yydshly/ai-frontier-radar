"""DailyBroadcast — rule-based broadcast script generator without LLM.

Produces a human-readable Chinese broadcast script from a DailyReportCard.
TTS audio generation is gated behind DAILY_BROADCAST_TTS_ENABLED.

No LLM is called. No external TTS API is called by default.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.application.radar.mimo_tts import MiMoTTSClient, MiMoTTSError


_AUDIO_FILENAME_RE = re.compile(
    r"^daily_broadcast_\d{4}-\d{2}-\d{2}_[0-9a-f]{12,24}\.wav$"
)


@dataclass(frozen=True)
class DailyBroadcastScript:
    """A broadcast-ready Chinese script derived from a DailyReportCard."""
    date_label: str
    title: str
    opening: str
    overview: str
    primary_sections: list[str]
    secondary_section: str | None
    closing: str
    full_text: str


@dataclass(frozen=True)
class DailyBroadcastAudioResult:
    """Result of a TTS audio generation attempt."""
    status: str  # disabled | generated | failed
    message: str
    audio_url: str | None = None
    audio_path: str | None = None


def build_daily_broadcast_script(
    date_label: str,
    total_items: int,
    covered_sources: int,
    with_zh_one_liner: int,
    with_insight_card: int,
    primary_items: list[dict],
    secondary_items: list[dict],
) -> DailyBroadcastScript:
    """Build a DailyBroadcastScript from a DailyReportCard.

    This function does NOT call any LLM.
    """
    # Title
    title = f"今日 AI 前沿播报，日期：{date_label}。"

    # Opening
    parts_ov: list[str] = []
    if total_items == 0:
        opening = "今天暂未发现新的 AI 前沿内容。"
    else:
        parts_ov.append(f"今天系统共发现 {total_items} 条 AI 前沿内容")
        if covered_sources > 0:
            parts_ov.append(f"覆盖 {covered_sources} 个来源")
        if with_zh_one_liner > 0:
            parts_ov.append(f"其中 {with_zh_one_liner} 条已有中文概述")
        if with_insight_card > 0:
            parts_ov.append(f"{with_insight_card} 条已有洞察卡")
        opening = "，".join(parts_ov) + "。"

    # Overview
    primary_count = len(primary_items)
    if primary_count > 0:
        overview = f"今天最值得关注的内容有 {primary_count} 条。"
    elif total_items > 0:
        overview = "今天发现的内容较为有限，暂无特别突出的重点条目。"
    else:
        overview = "今天暂无新增内容。"

    # Primary sections
    primary_sections: list[str] = []
    for idx, item in enumerate(primary_items, start=1):
        source_label = item.get("source_label", "")
        zh_one_liner = item.get("zh_one_liner")
        zh_summary = item.get("zh_summary")  # Prefer snapshot summary
        title_text = item.get("title", "无标题")
        related_directions = item.get("related_directions", [])
        url = item.get("url")
        insight_card_id = item.get("insight_card_id")
        item_id = item.get("item_id")

        section = _format_primary_item(
            index=idx,
            source_label=source_label,
            zh_one_liner=zh_one_liner,
            zh_summary=zh_summary,
            title=title_text,
            directions=related_directions,
            has_insight=bool(insight_card_id),
            has_url=bool(url),
            item_id=item_id,
        )
        primary_sections.append(section)

    # Secondary section
    secondary_section: str | None = None
    if secondary_items:
        brief_list: list[str] = []
        for item in secondary_items[:5]:
            source_label = item.get("source_label", "")
            title_text = item.get("title", "无标题")
            brief_list.append(f"来自 {source_label} 的《{title_text}》")
        secondary_section = "此外，今天还有其他值得扫一眼的内容，包括：" + "、".join(brief_list) + "。"
    elif total_items > primary_count:
        secondary_section = "此外，今天暂无其他次要内容，所有新增内容已进入今日必看。"
    else:
        secondary_section = None

    # Closing
    closing = _build_closing(primary_items, secondary_items)

    # Full text assembly
    full_parts: list[str] = [title, "", opening, "", overview, ""]
    for sec in primary_sections:
        full_parts.append(sec)
        full_parts.append("")
    if secondary_section:
        full_parts.append(secondary_section)
        full_parts.append("")
    full_parts.append(closing)
    full_text = "\n".join(full_parts)

    return DailyBroadcastScript(
        date_label=date_label,
        title=title,
        opening=opening,
        overview=overview,
        primary_sections=primary_sections,
        secondary_section=secondary_section,
        closing=closing,
        full_text=full_text,
    )


def build_core_report_broadcast_script(core_report: dict) -> DailyBroadcastScript:
    """Build a broadcast script from a persisted daily core report."""
    date_label = str(core_report.get("date_label") or "")
    report_title = str(core_report.get("title") or "今日 AI 前沿核心报告").strip()
    overview = str(core_report.get("overview") or "").strip()
    highlights = [
        str(item).strip()
        for item in core_report.get("highlights", [])
        if str(item).strip()
    ]
    title = f"{report_title}，日期：{date_label}。"
    opening = "以下是基于今日核心报告整理的语音摘要。"
    primary_sections = [
        f"第{_cn_number(index)}点，{highlight}"
        for index, highlight in enumerate(highlights, start=1)
    ]
    closing = "以上是今日核心报告语音摘要。你可以返回报告查看相关文章、洞察卡和原文。"
    full_parts = [title, "", opening]
    if overview:
        full_parts.extend(["", overview])
    for section in primary_sections:
        full_parts.extend(["", section])
    full_parts.extend(["", closing])

    return DailyBroadcastScript(
        date_label=date_label,
        title=title,
        opening=opening,
        overview=overview,
        primary_sections=primary_sections,
        secondary_section=None,
        closing=closing,
        full_text="\n".join(full_parts),
    )


def _format_primary_item(
    *,
    index: int,
    source_label: str,
    zh_one_liner: str | None,
    zh_summary: str | None,
    title: str,
    directions: list[str],
    has_insight: bool,
    has_url: bool,
    item_id: int,
) -> str:
    """Format one primary item as a broadcast paragraph."""
    lines: list[str] = []

    # Header
    lines.append(f"第{_cn_number(index)}条，来自 {source_label}。")

    # Main content — prefer zh_summary (from snapshot) over zh_one_liner
    display_text = zh_summary if zh_summary else zh_one_liner
    if display_text:
        # Truncate to 120 chars for broadcast
        if len(display_text) > 120:
            display_text = display_text[:117] + "..."
        lines.append(f"{display_text}")
    else:
        lines.append(f"《{title}》，这条内容尚未生成中文摘要，建议打开原文查看。")

    # Context
    context_parts: list[str] = []
    if directions:
        primary_dir = directions[0]
        context_parts.append(f"涉及 {primary_dir}")
    if has_insight:
        context_parts.append("已有洞察卡片")
    if context_parts:
        lines.append("，".join(context_parts) + "。")

    # Action hint
    if has_insight:
        lines.append("你可以打开原文或查看已有洞察卡。")
    elif display_text:
        lines.append("你可以打开原文阅读详细内容。")
    else:
        lines.append("建议打开原文查看完整内容。")

    return "".join(lines)


def _build_closing(primary_items: list[dict], secondary_items: list[dict]) -> str:
    """Build a closing suggestion paragraph."""
    if not primary_items:
        return "今天的播报就到这里，感谢收听。"

    # Find top directions
    all_directions: list[str] = []
    for item in primary_items:
        all_directions.extend(item.get("related_directions", [])[:2])

    suggestions: list[str] = []

    if all_directions:
        top_dir = all_directions[0]
        suggestions.append(f"优先查看和 {top_dir} 相关的内容")

    if len(primary_items) >= 2:
        suggestions.append(f"如果时间有限，先阅读今日必看中的第一条")

    has_insight_items = [i for i in primary_items if i.get("insight_card_id")]
    if has_insight_items:
        suggestions.append("已有洞察卡的条目值得关注")

    if suggestions:
        return "今天的建议是：" + "；".join(suggestions) + "。今天的播报就到这里，感谢收听。"
    return "今天的播报就到这里，感谢收听。"


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
    return str(n)


def generate_daily_broadcast_audio(
    script: DailyBroadcastScript,
    *,
    client: MiMoTTSClient | None = None,
    root_dir: str | Path | None = None,
) -> DailyBroadcastAudioResult:
    """Generate a WAV file from the broadcast script with MiMo V2.5 TTS."""
    enabled = os.getenv("DAILY_BROADCAST_TTS_ENABLED", "").strip().lower()
    if enabled != "true":
        return DailyBroadcastAudioResult(
            status="disabled",
            message="MiMo 语音合成未启用。请设置 DAILY_BROADCAST_TTS_ENABLED=true。",
        )

    try:
        tts_client = client or MiMoTTSClient()
        audio_dir = get_daily_broadcast_audio_dir(root_dir)
        audio_dir.mkdir(parents=True, exist_ok=True)
        settings = getattr(tts_client, "settings", None)
        fingerprint = "\n".join([
            script.full_text,
            str(getattr(settings, "model", "")),
            str(getattr(settings, "voice", "")),
            str(getattr(settings, "style", "")),
        ])
        digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:12]
        date_match = re.search(r"\d{4}-\d{2}-\d{2}", script.date_label)
        safe_date = date_match.group(0) if date_match else date.today().isoformat()
        filename = f"daily_broadcast_{safe_date}_{digest}.wav"
        audio_path = audio_dir / filename
        if _is_valid_wav_file(audio_path):
            return DailyBroadcastAudioResult(
                status="generated",
                message="已复用相同文稿的 MiMo V2.5 语音报告。",
                audio_url=f"/radar/daily-report/broadcast/audio/files/{filename}",
                audio_path=str(audio_path),
            )

        audio_bytes = tts_client.synthesize(script.full_text)
        if not _is_valid_wav_bytes(audio_bytes):
            raise MiMoTTSError("MiMo 返回的音频不是有效的 WAV 文件。")

        temp_path = audio_path.with_suffix(".wav.tmp")
        temp_path.write_bytes(audio_bytes)
        os.replace(temp_path, audio_path)
    except MiMoTTSError as exc:
        return DailyBroadcastAudioResult(status="failed", message=str(exc))
    except OSError:
        return DailyBroadcastAudioResult(
            status="failed",
            message="音频已生成，但保存文件失败，请检查运行目录权限。",
        )

    return DailyBroadcastAudioResult(
        status="generated",
        message="MiMo V2.5 语音报告已生成。",
        audio_url=f"/radar/daily-report/broadcast/audio/files/{filename}",
        audio_path=str(audio_path),
    )


def get_daily_broadcast_audio_dir(root_dir: str | Path | None = None) -> Path:
    """Return the private runtime directory used for generated audio."""
    if root_dir is not None:
        return Path(root_dir)
    configured = os.getenv("DAILY_BROADCAST_AUDIO_DIR", "").strip()
    project_root = Path(__file__).resolve().parents[3]
    if not configured:
        return project_root / "runtime" / "daily_audio"
    configured_path = Path(configured)
    return (
        configured_path
        if configured_path.is_absolute()
        else project_root / configured_path
    )


def get_daily_broadcast_audio_path(
    filename: str,
    *,
    root_dir: str | Path | None = None,
) -> Path | None:
    """Resolve a generated audio filename without allowing path traversal."""
    if not _AUDIO_FILENAME_RE.fullmatch(filename):
        return None
    return get_daily_broadcast_audio_dir(root_dir) / filename


def _is_valid_wav_bytes(audio_bytes: bytes) -> bool:
    return (
        len(audio_bytes) >= 44
        and audio_bytes.startswith(b"RIFF")
        and audio_bytes[8:12] == b"WAVE"
    )


def _is_valid_wav_file(path: Path) -> bool:
    try:
        with path.open("rb") as file_obj:
            return _is_valid_wav_bytes(file_obj.read(44))
    except OSError:
        return False


def is_valid_daily_broadcast_audio_file(path: Path) -> bool:
    """Return whether a generated audio path contains a valid WAV header."""
    return _is_valid_wav_file(path)
