"""Single read-only accessor for a SourceItem's content/summary/insight state.

C5 Phase 1: today the per-item state is derived independently in several places
(today_item_card, the radar reading panel, the source workspace, etc.), which
lets their judgments drift apart. This module is the one place that parses
``raw_metadata_json`` and reports the structured state, so callers delegate
instead of re-implementing the rules.

IMPORTANT — Phase 1 is behavior-preserving. ``read_item_state`` reproduces the
EXACT current semantics of ``today_item_card`` (notably: a Chinese detailed
summary is detected via the ``zh_summary`` key only; the historical alias
``summary_zh`` is NOT folded in here). Deliberately unifying key aliases is a
separate Phase 2 decision, because it would change what counts as "summarized".

Pure / read-only: no DB writes, no network, no LLM.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

# Metadata keys that, if present and non-empty, mean a content snapshot exists.
_CONTENT_TEXT_KEYS = (
    "raw_text_path",
    "content_snapshot",
    "content_text",
    "article_text",
    "full_text",
    "markdown_path",
)

# Source-provided summary keys (fallback tier below generated Chinese summaries).
_SOURCE_SUMMARY_KEYS = (
    "detail_description",
    "rss_summary",
    "rss_description",
    "description",
    "summary",
)


@dataclass(frozen=True)
class ItemSummaryState:
    state: str          # generated | source_summary | missing
    label: str
    has_one_liner: bool
    has_zh_summary: bool


@dataclass(frozen=True)
class ItemContentState:
    state: str          # queued | fetched | fetch_failed | not_fetched | unknown
    label: str
    note: str | None = None


@dataclass(frozen=True)
class ItemInsightState:
    state: str          # generated | has_card | eligible | has_summary | missing
    label: str
    insight_card_id: int | None = None


@dataclass(frozen=True)
class ItemState:
    summary: ItemSummaryState
    content: ItemContentState
    insight: ItemInsightState
    summary_generated: bool       # raw["summary_status"] == "generated"
    summary_basis: str | None     # raw["summary_basis"]


def _read_raw_metadata(item) -> dict[str, Any]:
    try:
        parsed = json.loads(item.raw_metadata_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _content_state(item, raw: dict[str, Any]) -> ItemContentState:
    explicit_status = str(raw.get("content_fetch_status") or "").strip()
    explicit_error = str(raw.get("content_fetch_error") or "").strip() or None

    if explicit_status == "queued":
        return ItemContentState("queued", "待获取", "正文获取已记录为待处理。")
    if explicit_status == "fetched":
        return ItemContentState("fetched", "已获取")
    if explicit_status in {"failed", "fetch_failed"}:
        return ItemContentState("fetch_failed", "获取失败", explicit_error)

    for key in _CONTENT_TEXT_KEYS:
        if _nonempty(raw.get(key)):
            return ItemContentState("fetched", "已获取")

    if item.url:
        return ItemContentState("not_fetched", "未获取")
    return ItemContentState("unknown", "无法判断", "当前条目没有可用于获取正文的 URL。")


def _summary_state(raw: dict[str, Any]) -> ItemSummaryState:
    has_one_liner = _nonempty(raw.get("zh_one_liner"))
    has_zh_summary = _nonempty(raw.get("zh_summary"))
    if has_zh_summary or has_one_liner:
        state, label = "generated", "已生成"
    elif any(_nonempty(raw.get(k)) for k in _SOURCE_SUMMARY_KEYS):
        state, label = "source_summary", "来源摘要"
    else:
        state, label = "missing", "待生成"
    return ItemSummaryState(state, label, has_one_liner, has_zh_summary)


def _insight_state(item, raw: dict[str, Any]) -> ItemInsightState:
    if item.insight_card_id:
        if raw.get("insight_status") == "generated":
            return ItemInsightState("generated", "已生成", item.insight_card_id)
        return ItemInsightState("has_card", "已有洞察卡", item.insight_card_id)
    if raw.get("summary_status") == "generated" and raw.get("summary_basis") == "html_snapshot":
        return ItemInsightState("eligible", "可生成", None)
    if raw.get("summary_status") == "generated":
        return ItemInsightState("has_summary", "已有摘要", None)
    return ItemInsightState("missing", "未生成", None)


def read_item_state(item) -> ItemState:
    """Parse a SourceItem's metadata once and return its structured state."""
    raw = _read_raw_metadata(item)
    return ItemState(
        summary=_summary_state(raw),
        content=_content_state(item, raw),
        insight=_insight_state(item, raw),
        summary_generated=raw.get("summary_status") == "generated",
        summary_basis=raw.get("summary_basis"),
    )
