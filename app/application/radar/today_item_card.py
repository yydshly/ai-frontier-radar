"""Display state for Today Radar item cards.

Pure view helpers only: no DB access, no network, no LLM, no writes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.application.candidates.display import CandidateDisplayCard
from app.application.source_items.item_state import read_item_state
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
    zh_one_liner_state: str
    zh_one_liner_label: str
    zh_summary_state: str
    zh_summary_label: str
    overview_state: str
    overview_label: str
    detailed_summary_state: str
    detailed_summary_label: str
    content_state: str
    insight_state: str
    primary_text: str | None
    can_open_original: bool
    can_fetch_content: bool
    can_generate_summary: bool
    can_generate_insight: bool
    fetch_method_label: str = "来源探测"
    summary_label: str = "待生成"
    content_label: str = "未获取"
    content_note: str | None = None
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
    """Infer the content-fetch state from SourceItem metadata.

    Delegates to the canonical ``read_item_state`` accessor (C5 Phase 1).
    """
    c = read_item_state(item).content
    return TodayItemContentState(c.state, c.label, c.note)


def _generated_or_missing(value: Any) -> tuple[str, str]:
    if isinstance(value, str) and value.strip():
        return "generated", "已生成"
    return "missing", "待生成"


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
    state = read_item_state(item)
    summary_state, summary_label = state.summary.state, state.summary.label
    zh_one_liner_state, zh_one_liner_label = _generated_or_missing(raw.get("zh_one_liner"))
    zh_summary_state, zh_summary_label = _generated_or_missing(raw.get("zh_summary"))
    content = TodayItemContentState(state.content.state, state.content.label, state.content.note)
    insight_state, insight_label = state.insight.state, state.insight.label

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

    # can_generate_summary: True when content is fetched but no summary yet
    content_fetched = content.state == "fetched"
    summary_generated = state.summary_generated
    can_generate_summary = bool(item.url) and content_fetched and not summary_generated

    # can_generate_insight: True when summary exists but no insight card yet
    can_generate_insight = (
        not item.insight_card_id
        and summary_generated
        and state.summary_basis == "html_snapshot"
    )

    return TodayItemCard(
        item_id=item.id,
        title=title,
        source_key=item.source_key,
        url=item.url,
        first_seen_label=_format_datetime(item.first_seen_at) or "发现时间未知",
        published_label=_format_datetime(item.published_at),
        summary_state=summary_state,
        zh_one_liner_state=zh_one_liner_state,
        zh_one_liner_label=zh_one_liner_label,
        zh_summary_state=zh_summary_state,
        zh_summary_label=zh_summary_label,
        overview_state=zh_one_liner_state,
        overview_label=zh_one_liner_label,
        detailed_summary_state=zh_summary_state,
        detailed_summary_label=zh_summary_label,
        content_state=content.state,
        insight_state=insight_state,
        primary_text=primary_text,
        can_open_original=bool(item.url),
        can_fetch_content=bool(item.url) and content.state in {"not_fetched", "fetch_failed"},
        can_generate_summary=can_generate_summary,
        can_generate_insight=can_generate_insight,
        fetch_method_label=_fetch_method_label(raw),
        summary_label=summary_label,
        content_label=content.label,
        content_note=content.note,
        insight_label=insight_label,
    )
