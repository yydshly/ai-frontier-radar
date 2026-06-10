"""DailyReportCard — rule-based daily report card without LLM.

Produces a two-tier report:
- Primary: top 3-5 items ("今日必看") with reason explanations
- Secondary: remaining ranked items ("其他值得扫一眼") with brief tags

No LLM is called. Uses source weight, keyword matching, and freshness scoring.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.models import SourceItem


# Strong-signal keywords that indicate an important report.
_STRONG_SIGNAL_KEYWORDS = {
    "report", "benchmark", "safety", "agent", "model", "release",
    "evaluation", "research", "roadmap", "paper", "policy",
    "open source", "multimodal", "voice", "video", "coding", "developer",
    "fine-tuning", "pre-training", "alignment", "dataset", "architecture",
    "inference", "deployment", "production", "privacy", "security",
    "law", "regulation", "government", "startup", "funding", "acquisition",
}

# User interest direction keywords.
_INTEREST_KEYWORDS = {
    "ai coding", "agent", "multi-agent", "rag", "knowledge base",
    "document understanding", "tts", "voice", "video", "ai safety",
    "claude", "anthropic", "openai", "deepmind", "minimax", "mistral",
    "google", "meta", "microsoft", "nvidia", "amazon", "apple",
    "hugging face", "stability ai", " Cohere", "replicate", "LangChain",
    "embedding", "vector", "chunking", "retrieval", "generation",
    "synthetic data", "data engineering", "pipeline", "finetuning",
}

# Source weight: higher = more important source for ranking.
_SOURCE_WEIGHTS: dict[str, float] = {
    "openai_news": 2.0,
    "anthropic_news": 2.0,
    "deepmind_blog": 2.0,
    "huggingface_blog": 1.8,
    "meta_ai_blog": 1.8,
    "nvidia_ai_blog": 1.8,
    "microsoft_ai_source": 1.7,
    "stanford_hai": 1.5,
    "mit_news_ai": 1.5,
    "arxiv_cs_ai": 1.2,
    "arxiv_cs_cl": 1.0,
    "arxiv_cs_lg": 1.0,
    "mistral_ai_news": 1.5,
    "cohere_blog": 1.5,
    "berkeley_bair_blog": 1.3,
}


@dataclass(frozen=True)
class DailyReportPrimaryItem:
    """A top-ranked "must read" item."""
    item_id: int
    title: str
    source_key: str
    url: str | None
    zh_one_liner: str | None
    reason: str
    related_directions: list[str] = field(default_factory=list)
    suggested_action: str | None = None


@dataclass(frozen=True)
class DailyReportSecondaryItem:
    """A ranked item for the secondary "worth a glance" list."""
    item_id: int
    title: str
    source_key: str
    url: str | None
    brief: str | None
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DailyReportOverview:
    """Today's collection statistics."""
    total_items: int
    with_zh_one_liner: int
    with_zh_summary: int
    with_insight_card: int
    covered_sources: int


@dataclass(frozen=True)
class DailyReportCard:
    """Complete daily report card with two-tier items."""
    date_label: str
    overview: DailyReportOverview
    primary_items: list[DailyReportPrimaryItem] = field(default_factory=list)
    secondary_items: list[DailyReportSecondaryItem] = field(default_factory=list)


def _read_raw_metadata(item: SourceItem) -> dict[str, Any]:
    try:
        parsed = json.loads(item.raw_metadata_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _hours_old(dt, now: datetime) -> float:
    """Return hours between dt and now; dt may be a datetime or a ISO-format string."""
    if dt is None:
        return 0.0
    if isinstance(dt, datetime):
        ref = dt
    else:
        try:
            ref = datetime.fromisoformat(str(dt))
        except (ValueError, TypeError):
            return 0.0
    try:
        return max(0.0, (now - ref).total_seconds() / 3600)
    except (TypeError, OSError):
        return 0.0


def _score_item(item: SourceItem, now: datetime) -> float:
    """Score a SourceItem for ranking. Higher = more important."""
    raw = _read_raw_metadata(item)

    # 1. Source weight (most significant factor).
    source_weight = _SOURCE_WEIGHTS.get(item.source_key, 1.0)

    # 2. Strong-signal keyword match.
    title_lower = (item.title or "").lower()
    signal_matches = sum(
        1 for kw in _STRONG_SIGNAL_KEYWORDS
        if kw in title_lower
    )

    # 3. User interest keyword match.
    interest_matches = sum(
        1 for kw in _INTEREST_KEYWORDS
        if kw in title_lower
    )

    # 4. Content availability bonuses.
    has_one_liner = bool(str(raw.get("zh_one_liner") or "").strip())
    has_summary = bool(str(raw.get("zh_summary") or "").strip())
    has_insight = item.status == "compiled" and item.insight_card_id
    content_bonus = (has_one_liner * 0.5) + (has_summary * 0.3) + (has_insight * 1.0)

    # 5. Freshness: prefer newer items.
    hours_old = _hours_old(item.published_at or item.first_seen_at, now)
    freshness = math.exp(-hours_old / 48)  # decay half-life ~48h

    return (
        source_weight * 3.0
        + signal_matches * 1.5
        + interest_matches * 1.0
        + content_bonus
        + freshness * 2.0
    )


def _extract_keywords(text: str) -> list[str]:
    """Extract matching keywords from text."""
    text_lower = text.lower()
    matched: list[str] = []
    for kw in _STRONG_SIGNAL_KEYWORDS | _INTEREST_KEYWORDS:
        if kw in text_lower:
            matched.append(kw)
    return matched[:5]  # cap at 5


def _build_reason(title: str, matched_keywords: list[str], source_key: str) -> str:
    """Build a human-readable reason string."""
    if not matched_keywords:
        parts = [f"来自{source_key}的更新"]
    else:
        keyword_str = "、".join(matched_keywords[:3])
        parts = [f"涉及{keyword_str}"]
        if source_key in _SOURCE_WEIGHTS and _SOURCE_WEIGHTS[source_key] >= 1.8:
            parts.append("重要来源")
    return "，".join(parts) if parts else "今日更新"


def build_daily_report_card(
    db,
    *,
    now: datetime | None = None,
    primary_limit: int = 5,
    secondary_limit: int = 10,
) -> DailyReportCard:
    """Build a DailyReportCard from today's SourceItems using rule-based ranking.

    This function does NOT call any LLM.
    """
    if now is None:
        now = datetime.utcnow()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Query today's items.
    rows = (
        db.query(SourceItem)
        .filter(SourceItem.first_seen_at >= day_start)
        .order_by(SourceItem.first_seen_at.desc())
        .all()
    )

    if not rows:
        return DailyReportCard(
            date_label=day_start.strftime("%Y-%m-%d"),
            overview=DailyReportOverview(
                total_items=0,
                with_zh_one_liner=0,
                with_zh_summary=0,
                with_insight_card=0,
                covered_sources=0,
            ),
        )

    # Score and sort.
    scored = [(_score_item(r, now), r) for r in rows]
    scored.sort(key=lambda x: x[0], reverse=True)

    # Build overview.
    source_keys: set[str] = set()
    with_one_liner = 0
    with_summary = 0
    with_insight = 0
    for item in rows:
        raw = _read_raw_metadata(item)
        source_keys.add(item.source_key)
        if str(raw.get("zh_one_liner") or "").strip():
            with_one_liner += 1
        if str(raw.get("zh_summary") or "").strip():
            with_summary += 1
        if item.status == "compiled" and item.insight_card_id:
            with_insight += 1

    overview = DailyReportOverview(
        total_items=len(rows),
        with_zh_one_liner=with_one_liner,
        with_zh_summary=with_summary,
        with_insight_card=with_insight,
        covered_sources=len(source_keys),
    )

    # Top items = primary.
    primary_rows = [r for _, r in scored[:primary_limit]]
    primary_items: list[DailyReportPrimaryItem] = []
    for item in primary_rows:
        raw = _read_raw_metadata(item)
        title = item.title or "无标题"
        keywords = _extract_keywords(title)
        reason = _build_reason(title, keywords, item.source_key)
        zh_one_liner = str(raw.get("zh_one_liner") or "").strip() or None
        related = keywords[:3] if keywords else []

        # Suggested action based on state.
        if item.status == "compiled" and item.insight_card_id:
            suggested = "查看 InsightCard"
        elif zh_one_liner:
            suggested = "阅读中文概述"
        else:
            suggested = "打开原文"

        primary_items.append(DailyReportPrimaryItem(
            item_id=item.id,
            title=title,
            source_key=item.source_key,
            url=item.url,
            zh_one_liner=zh_one_liner,
            reason=reason,
            related_directions=related,
            suggested_action=suggested,
        ))

    # Remaining = secondary.
    secondary_rows = [r for _, r in scored[primary_limit:primary_limit + secondary_limit]]
    secondary_items: list[DailyReportSecondaryItem] = []
    for item in secondary_rows:
        raw = _read_raw_metadata(item)
        title = item.title or "无标题"
        keywords = _extract_keywords(title)
        brief = str(raw.get("zh_one_liner") or "").strip() or str(
            raw.get("zh_summary") or "").strip() or None
        secondary_items.append(DailyReportSecondaryItem(
            item_id=item.id,
            title=title,
            source_key=item.source_key,
            url=item.url,
            brief=brief,
            tags=keywords[:3],
        ))

    return DailyReportCard(
        date_label=day_start.strftime("%Y-%m-%d"),
        overview=overview,
        primary_items=primary_items,
        secondary_items=secondary_items,
    )
