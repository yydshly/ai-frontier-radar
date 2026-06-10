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
    "hugging face", "stability ai", "cohere", "replicate", "LangChain",
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

# Source key → user-friendly display name.
_SOURCE_DISPLAY_NAMES: dict[str, str] = {
    "openai_news": "OpenAI",
    "anthropic_news": "Anthropic",
    "deepmind_blog": "Google DeepMind",
    "huggingface_blog": "Hugging Face",
    "meta_ai_blog": "Meta AI",
    "nvidia_ai_blog": "NVIDIA AI",
    "microsoft_ai_source": "Microsoft AI",
    "stanford_hai": "Stanford HAI",
    "mit_news_ai": "MIT AI",
    "arxiv_cs_ai": "arXiv CS.AI",
    "arxiv_cs_cl": "arXiv CS.CL",
    "arxiv_cs_lg": "arXiv CS.LG",
    "mistral_ai_news": "Mistral AI",
    "cohere_blog": "Cohere",
    "berkeley_bair_blog": "Berkeley BAIR",
}

# Keyword → Chinese label mapping for display.
_DIRECTION_LABELS: dict[str, str] = {
    # Agent / workflow
    "agent": "Agent 工作流",
    "multi-agent": "多 Agent",
    # Knowledge
    "rag": "RAG / 知识库",
    "knowledge base": "知识库",
    "document understanding": "文档理解",
    "embedding": "向量 Embedding",
    "vector": "向量检索",
    "retrieval": "检索增强",
    # Voice / Audio
    "tts": "语音 / TTS",
    "voice": "语音产品",
    # Video
    "video": "视频生成",
    # Coding
    "coding": "AI 编程",
    "developer": "开发者工具",
    "open source": "开源",
    # Safety
    "ai safety": "AI 安全",
    "safety": "AI 安全",
    # Model releases
    "model": "模型发布",
    "release": "模型发布",
    "benchmark": "评测基准",
    "evaluation": "评测基准",
    "research": "研究报告",
    "roadmap": "路线图",
    "paper": "论文",
    "architecture": "模型架构",
    "fine-tuning": "微调",
    "pre-training": "预训练",
    "alignment": "对齐研究",
    "dataset": "数据集",
    "inference": "推理优化",
    "deployment": "部署落地",
    "production": "生产应用",
    "synthetic data": "合成数据",
    "data engineering": "数据工程",
    "pipeline": "流程编排",
    "multimodal": "多模态",
    "policy": "政策 / 产业",
    "law": "政策法规",
    "regulation": "政策法规",
    "government": "政府动态",
    "privacy": "隐私安全",
    "security": "隐私安全",
    "startup": "创业投资",
    "funding": "创业投资",
    "acquisition": "收购并购",
    "generation": "内容生成",
    "LangChain": "LangChain",
    # Companies (not direction labels — for source display)
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "claude": "Claude",
    "deepmind": "DeepMind",
    "minimax": "MiniMax",
    "mistral": "Mistral",
    "google": "Google",
    "meta": "Meta",
    "microsoft": "Microsoft",
    "nvidia": "NVIDIA",
    "amazon": "Amazon",
    "apple": "Apple",
    "hugging face": "Hugging Face",
    "stability ai": "Stability AI",
    "cohere": "Cohere",
    "replicate": "Replicate",
}


# Primary card limits.
_PRIMARY_MIN = 3
_PRIMARY_MAX = 5


@dataclass(frozen=True)
class DailyReportPrimaryItem:
    """A top-ranked "must read" item."""
    item_id: int
    insight_card_id: int | None
    title: str
    source_key: str
    source_label: str
    url: str | None
    zh_one_liner: str | None
    zh_summary: str | None  # From snapshot summary, preferred over zh_one_liner
    reason: str
    related_directions: list[str] = field(default_factory=list)
    suggested_action: str | None = None


@dataclass(frozen=True)
class DailyReportSecondaryItem:
    """A ranked item for the secondary "worth a glance" list."""
    item_id: int
    title: str
    source_key: str
    source_label: str
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
    secondary_all_shown: bool = True


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

    source_weight = _SOURCE_WEIGHTS.get(item.source_key, 1.0)
    title_lower = (item.title or "").lower()

    signal_matches = sum(
        1 for kw in _STRONG_SIGNAL_KEYWORDS
        if kw in title_lower
    )

    interest_matches = sum(
        1 for kw in _INTEREST_KEYWORDS
        if kw in title_lower
    )

    has_one_liner = bool(str(raw.get("zh_one_liner") or "").strip())
    has_summary = bool(str(raw.get("zh_summary") or "").strip())
    has_insight = item.status == "compiled" and item.insight_card_id
    content_bonus = (has_one_liner * 0.5) + (has_summary * 0.3) + (has_insight * 1.0)

    hours_old_val = _hours_old(item.published_at or item.first_seen_at, now)
    freshness = math.exp(-hours_old_val / 48)

    return (
        source_weight * 3.0
        + signal_matches * 1.5
        + interest_matches * 1.0
        + content_bonus
        + freshness * 2.0
    )


def _extract_directions(text: str) -> list[str]:
    """Extract matching keywords and return Chinese labels."""
    text_lower = text.lower()
    matched: list[str] = []
    seen: set[str] = set()
    for kw in _STRONG_SIGNAL_KEYWORDS | _INTEREST_KEYWORDS:
        if kw in text_lower and kw not in seen:
            label = _DIRECTION_LABELS.get(kw, kw)
            if label not in seen:
                matched.append(label)
                seen.add(label)
    return matched[:5]


def _build_reason(source_key: str, directions: list[str], has_insight: bool) -> str:
    """Build a natural Chinese reason sentence for a primary item."""
    source_weight = _SOURCE_WEIGHTS.get(source_key, 1.0)
    is_high_weight = source_weight >= 1.8
    source_label = _SOURCE_DISPLAY_NAMES.get(source_key, source_key)

    parts: list[str] = []

    # High-weight source gets mentioned by name
    if is_high_weight:
        parts.append(f"来自 {source_label} 官方来源")
    elif directions:
        parts.append(f"来自 {source_label}")

    # Add direction context
    if directions:
        # Pick the most meaningful direction for the reason
        primary_dir = directions[0]
        parts.append(f"涉及 {primary_dir}")

    if has_insight:
        parts.append("已有洞察卡片")

    result = "，".join(parts)
    return result if result else "今日重要更新"


def _source_label(source_key: str) -> str:
    """Return user-friendly source name."""
    return _SOURCE_DISPLAY_NAMES.get(source_key, source_key)


def build_daily_report_card(
    db,
    *,
    now: datetime | None = None,
    primary_min: int = _PRIMARY_MIN,
    primary_max: int = _PRIMARY_MAX,
    secondary_limit: int = 10,
) -> DailyReportCard:
    """Build a DailyReportCard from today's SourceItems using rule-based ranking.

    This function does NOT call any LLM.
    """
    if now is None:
        now = datetime.utcnow()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

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

    scored = [(_score_item(r, now), r) for r in rows]
    scored.sort(key=lambda x: x[0], reverse=True)

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

    total = len(rows)
    if total >= primary_min:
        primary_count = min(primary_max, max(primary_min, total))
    else:
        primary_count = total

    primary_rows = [r for _, r in scored[:primary_count]]
    primary_items: list[DailyReportPrimaryItem] = []
    for item in primary_rows:
        raw = _read_raw_metadata(item)
        title = item.title or "无标题"
        directions = _extract_directions(title)
        has_insight = item.status == "compiled" and item.insight_card_id
        reason = _build_reason(item.source_key, directions, has_insight)
        zh_one_liner = str(raw.get("zh_one_liner") or "").strip() or None
        # Prefer snapshot-generated zh_summary over one-liner
        summary_basis = raw.get("summary_basis")
        zh_summary = str(raw.get("zh_summary") or "").strip() or None if summary_basis == "html_snapshot" else None

        if has_insight:
            suggested = "查看洞察卡"
        elif zh_summary:
            suggested = "阅读正文摘要"
        elif zh_one_liner:
            suggested = "阅读中文概述"
        else:
            suggested = "打开原文"

        primary_items.append(DailyReportPrimaryItem(
            item_id=item.id,
            insight_card_id=item.insight_card_id if has_insight else None,
            title=title,
            source_key=item.source_key,
            source_label=_source_label(item.source_key),
            url=item.url,
            zh_one_liner=zh_one_liner,
            zh_summary=zh_summary,
            reason=reason,
            related_directions=directions[:3],
            suggested_action=suggested,
        ))

    secondary_rows = [r for _, r in scored[primary_count:primary_count + secondary_limit]]
    secondary_items: list[DailyReportSecondaryItem] = []
    for item in secondary_rows:
        raw = _read_raw_metadata(item)
        title = item.title or "无标题"
        directions = _extract_directions(title)
        brief = str(raw.get("zh_one_liner") or "").strip() or str(
            raw.get("zh_summary") or "").strip() or None
        secondary_items.append(DailyReportSecondaryItem(
            item_id=item.id,
            title=title,
            source_key=item.source_key,
            source_label=_source_label(item.source_key),
            url=item.url,
            brief=brief,
            tags=directions[:3],
        ))

    # secondary_all_shown = True means all remaining items are shown (no truncation)
    secondary_all_shown = len(scored) <= primary_count + secondary_limit

    return DailyReportCard(
        date_label=day_start.strftime("%Y-%m-%d"),
        overview=overview,
        primary_items=primary_items,
        secondary_items=secondary_items,
        secondary_all_shown=secondary_all_shown,
    )
