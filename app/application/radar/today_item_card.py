"""Display state for Today Radar item cards.

Pure view helpers only: no DB access, no network, no LLM, no writes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.application.candidates.display import CandidateDisplayCard
from app.models import SourceItem


@dataclass(frozen=True)
class TodayItemContentState:
    state: str
    label: str
    note: str | None = None


@dataclass(frozen=True)
class TodayItemCard:
    item_id: int
    title: str
    source_key: str
    url: str | None
    first_seen_label: str
    published_label: str | None
    summary_state: str
    content_state: str
    insight_state: str
    primary_text: str | None
    can_open_original: bool
    can_fetch_content: bool
    can_generate_insight: bool
    fetch_method_label: str = "来源探测"
    summary_label: str = "待生成"
    content_label: str = "未获取"
    insight_label: str = "未生成"


def _read_raw_metadata(item: SourceItem) -> dict[str, Any]:
    try:
        parsed = json.loads(item.raw_metadata_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _format_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%m-%d %H:%M")
    text = str(value).strip()
    return text or None


def build_today_item_content_state(item: SourceItem) -> TodayItemContentState:
    """Infer the content-fetch state from SourceItem metadata."""
    raw = _read_raw_metadata(item)
    explicit_status = str(raw.get("content_fetch_status") or "").strip()
    explicit_error = str(raw.get("content_fetch_error") or "").strip() or None

    if explicit_status == "queued":
        return TodayItemContentState("queued", "等待获取", "正文获取已记录为待处理。")
    if explicit_status == "fetched":
        return TodayItemContentState("fetched", "已获取")
    if explicit_status in {"failed", "fetch_failed"}:
        return TodayItemContentState("fetch_failed", "获取失败", explicit_error)

    for key in (
        "raw_text_path",
        "content_snapshot",
        "content_text",
        "article_text",
        "full_text",
        "markdown_path",
    ):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return TodayItemContentState("fetched", "已获取")

    if item.url:
        return TodayItemContentState("not_fetched", "未获取")
    return TodayItemContentState("unknown", "无法判断", "当前条目没有可用于获取正文的 URL。")


def _summary_state(raw: dict[str, Any]) -> tuple[str, str]:
    if str(raw.get("zh_summary") or "").strip() or str(raw.get("zh_one_liner") or "").strip():
        return "generated", "已生成"
    for key in ("detail_description", "rss_summary", "rss_description", "description", "summary"):
        if str(raw.get(key) or "").strip():
            return "source_summary", "来源摘要"
    return "missing", "待生成"


def _insight_state(item: SourceItem) -> tuple[str, str]:
    if item.status == "compiled" and item.insight_card_id:
        return "generated", "已生成"
    if item.status == "compiling":
        return "compiling", "生成中"
    if item.status == "failed":
        return "failed", "生成失败"
    return "missing", "未生成"


def _fetch_method_label(raw: dict[str, Any]) -> str:
    strategy = str(
        raw.get("fetch_strategy")
        or raw.get("source_fetch_strategy")
        or raw.get("get_method")
        or ""
    ).strip()
    if strategy == "rss":
        return "RSS"
    if strategy == "html_index":
        return "网页索引"
    if strategy:
        return strategy
    return "来源探测"


def build_today_item_card(
    item: SourceItem,
    display_card: CandidateDisplayCard | None = None,
) -> TodayItemCard:
    """Build a TodayItemCard from a SourceItem and optional display card."""
    raw = _read_raw_metadata(item)
    summary_state, summary_label = _summary_state(raw)
    content = build_today_item_content_state(item)
    insight_state, insight_label = _insight_state(item)

    title = (
        (display_card.title if display_card else None)
        or item.title
        or "无标题"
    )
    primary_text = (
        (display_card.primary_text if display_card else None)
        or str(raw.get("zh_one_liner") or "").strip()
        or None
    )

    return TodayItemCard(
        item_id=item.id,
        title=title,
        source_key=item.source_key,
        url=item.url,
        first_seen_label=_format_datetime(item.first_seen_at) or "发现时间未知",
        published_label=_format_datetime(item.published_at),
        summary_state=summary_state,
        content_state=content.state,
        insight_state=insight_state,
        primary_text=primary_text,
        can_open_original=bool(item.url),
        can_fetch_content=bool(item.url) and content.state in {"not_fetched", "fetch_failed"},
        can_generate_insight=item.status == "discovered",
        fetch_method_label=_fetch_method_label(raw),
        summary_label=summary_label,
        content_label=content.label,
        insight_label=insight_label,
    )
