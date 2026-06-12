"""Compile candidate selection — reusable scoring and ranking logic.

V1.0-beta.16 Phase 4.4.

Does NOT call LLM. Does NOT modify database state.
Does NOT auto-compile. Returns scored candidates for display only.

Used by:
- scripts/select_today_compile_candidates.py (CLI)
- RadarTodayService (web page /radar/today)
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

# ── Scoring constants ───────────────────────────────────────────────────────────

# Source priority comes from the single source-importance table (C1 Phase C).
from app.application.radar.relevance import source_priority


def _stale_published_days() -> int:
    """Items published more than this many days ago are down-ranked (staleness
    guard). Defaults to 7 (design §8.8); override with RADAR_RECOMMEND_STALE_DAYS."""
    raw = os.getenv("RADAR_RECOMMEND_STALE_DAYS")
    try:
        value = int(raw) if raw is not None else 7
    except (TypeError, ValueError):
        return 7
    return value if 1 <= value <= 365 else 7


def _published_age_days(published_at, now: datetime) -> float | None:
    """Age in days from a SourceItem.published_at, or None if unparseable.

    published_at is free-text (RFC822 or ISO, ~90% parseable, ~9% missing); when
    it can't be parsed we return None and apply no penalty (fetch time stays the
    primary signal — see the increment model design, time-basis decision).
    """
    if not published_at:
        return None
    parsed: datetime | None = None
    if isinstance(published_at, datetime):
        parsed = published_at
    elif isinstance(published_at, str) and published_at.strip():
        text = published_at.strip()
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            parsed = None
        if parsed is None:
            try:
                parsed = datetime.fromisoformat(text)
            except (TypeError, ValueError):
                parsed = None
    if parsed is None:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return (now - parsed).total_seconds() / 86400.0

# Keywords that suggest high-value content (in title or URL)
_TOPIC_KEYWORDS = [
    "coding", "codex", "developer", "agent", "workflow", "rag", "retrieval",
    "document", "pdf", "tts", "voice", "audio", "video", "safety", "policy",
    "openai", "anthropic", "deepmind", "gemini", "claude", "minimax",
    "mistral", "cohere", "huggingface", "arxiv",
    "llm", "gpt", "benchmark",
    "reasoning", "chain-of-thought", "inference",
    "multimodal", "vision", "image", "speech",
    "alignment", "rlhf", "fine-tuning", "training",
    "memory", "context", "attention", "transformer",
    "robotics", "embodied", "planning",
]

# Weak/泛 titles
_WEAK_TITLES = frozenset(
    w.lower() for w in (
        "news", "blog", "update", "featured", "learn more", "read more",
        "more", "view", "explore", "see more", "continue reading",
        "details", "overview", "welcome", "home",
    )
)

# Blocked domains / sources
_BLOCKED_SOURCES = {"test_v10_demo"}
_BLOCKED_DOMAINS = {"example.com", "localhost"}


# ── Dataclasses ────────────────────────────────────────────────────────────────


@dataclass
class CompileCandidate:
    """A single compile candidate with scoring metadata."""
    rank: int
    source_item_id: int
    source_key: str
    title: str
    url: str
    score: int
    reasons: list[str]
    compile_basis: str  # "metadata" | "fulltext"
    published_at: str | None
    first_seen_at: str | None
    summary_preview: str | None = None  # zh_one_liner or zh_summary preview (max 120 chars)
    reason_labels: list[str] = field(default_factory=list)
    compile_basis_label: str = "来源信息"


# ── Candidate selection logic ─────────────────────────────────────────────────


def select_compile_candidates(
    db,
    hours: int = 24,
    limit: int = 10,
    per_source_limit: int = 3,
    max_scan: int = 300,
    item_ids: set[int] | None = None,
    include_processed: bool = False,
) -> list[CompileCandidate]:
    """Select and rank top compile candidates. Read-only.

    Args:
        db: SQLAlchemy session.
        hours: Time window in hours (default 24).
        limit: Maximum number of candidates to return (default 10).
        per_source_limit: Max candidates per source_key (default 3).
        max_scan: Maximum SourceItems to fetch from DB for scoring (default 300).
                  Filtering happens in the SQL layer to avoid loading all items.
        include_processed: Include items that are compiling, compiled, or failed.
                           Use this for a stable recommendation view; generation
                           queues should keep the default pending-only behavior.

    Returns:
        List of CompileCandidate sorted by score descending, capped by per_source_limit.
    """
    from app.models import SourceItem, Source
    from app.application.content.content_snapshot import get_snapshot_path

    cutoff = datetime.utcnow() - timedelta(hours=hours)
    now = datetime.utcnow()

    # Load enabled sources for filtering (small set, always safe to load all)
    enabled_sources = {
        s.id: s.source_key
        for s in db.query(Source).filter(Source.enabled.is_(True)).all()
    }
    enabled_ids = set(enabled_sources.keys())

    # DB-layer filters: status, no existing card, has title, has url, in time window.
    # Blocked sources/domains and weak titles are checked in Python (lightweight).
    # Result is ordered by first_seen_at desc and limited to max_scan.
    query = db.query(SourceItem).filter(
            SourceItem.title.isnot(None),
            SourceItem.title != "",
            SourceItem.url.isnot(None),
            SourceItem.url != "",
            (SourceItem.first_seen_at >= cutoff) | (SourceItem.last_seen_at >= cutoff),
        )
    if not include_processed:
        query = query.filter(
            SourceItem.status.in_(("discovered", "fetched")),
            SourceItem.insight_card_id.is_(None),
        )
    if item_ids is not None:
        if not item_ids:
            return []
        query = query.filter(SourceItem.id.in_(item_ids))

    candidate_items = (
        query
        .order_by(SourceItem.first_seen_at.desc())
        .limit(max_scan)
        .all()
    )

    scored: list[tuple[int, dict]] = []  # (score, item_dict)

    for item in candidate_items:
        # Blocked sources
        if item.source_key in _BLOCKED_SOURCES:
            continue
        # Must be from an enabled source
        if item.source_id not in enabled_ids:
            continue
        # Check blocked domains
        url_lower = item.url.lower()
        if any(b in url_lower for b in _BLOCKED_DOMAINS):
            continue

        # Determine compile basis
        has_snapshot = get_snapshot_path(item.id).exists()
        compile_basis = "fulltext" if has_snapshot else "metadata"

        # Parse raw_metadata for rich text detection
        raw = item.raw_metadata_json
        meta: dict[str, Any] = {}
        rich_text = ""
        if raw:
            try:
                parsed = json.loads(raw)
                meta = parsed if isinstance(parsed, dict) else {}
                for field_name in ("zh_summary", "summary_zh", "zh_one_liner",
                                   "summary", "rss_summary", "description",
                                   "detail_description", "content_snippet"):
                    val = meta.get(field_name, "")
                    if val and len(str(val)) >= 50:
                        rich_text = str(val)
                        break
            except Exception:
                pass

        # Compute score
        score = 0
        reasons: list[str] = []

        # Topic keyword match
        title_lower = (item.title or "").lower()
        url_lower = (item.url or "").lower()
        topic_hits = [kw for kw in _TOPIC_KEYWORDS if kw in title_lower or kw in url_lower]
        if topic_hits:
            score += min(len(topic_hits), 4) * 8
            reasons.append(f"topic_match({len(topic_hits)})")

        # Rich metadata text
        if rich_text:
            score += 20
            reasons.append("rich_metadata")
        elif compile_basis == "fulltext":
            score += 15
            reasons.append("has_snapshot")

        # Source priority
        src_score = source_priority(item.source_key)
        if src_score > 0:
            score += src_score
            reasons.append(f"source_priority({item.source_key}={src_score})")

        # Recency
        if item.first_seen_at:
            age_hours = (now - item.first_seen_at).total_seconds() / 3600
            if age_hours < 1:
                score += 10
                reasons.append("fresh(<1h)")
            elif age_hours < 6:
                score += 6
                reasons.append("fresh(<6h)")

        # Staleness guard (design §8.8): down-rank items whose PUBLISH time is
        # clearly old, so a freshly-fetched backlog (newly-added source / bootstrap)
        # can't masquerade as fresh in the recommendations. Fetch time stays the
        # primary signal; this only applies when published_at is parseable.
        _stale_days = _stale_published_days()
        _age_days = _published_age_days(item.published_at, now)
        if _age_days is not None and _age_days > _stale_days:
            score -= 15
            reasons.append(f"stale_published(>{_stale_days}d)")

        # Title quality penalties
        if _is_weak_title(item.title):
            score -= 20
            reasons.append("weak_title")

        # Build summary_preview: zh_summary > zh_one_liner > zh_summary from metadata > first 80 chars of source summary
        summary_preview = _build_summary_preview(meta)

        item_dict = {
            "item": item,
            "score": score,
            "reasons": reasons,
            "compile_basis": compile_basis,
            "rich_text": rich_text,
            "summary_preview": summary_preview,
        }
        scored.append((score, item_dict))

    # Sort by score descending
    scored.sort(key=lambda x: -x[0])

    # Per-source limit + final ranking
    source_counts: dict[str, int] = defaultdict(int)
    results: list[CompileCandidate] = []
    for score, item_dict in scored:
        item: SourceItem = item_dict["item"]
        if source_counts[item.source_key] >= per_source_limit:
            continue
        source_counts[item.source_key] += 1

        results.append(CompileCandidate(
            rank=len(results) + 1,
            source_item_id=item.id,
            source_key=item.source_key,
            title=item.title or "",
            url=item.url or "",
            score=score,
            reasons=item_dict["reasons"],
            compile_basis=item_dict["compile_basis"],
            published_at=str(item.published_at) if item.published_at else None,
            first_seen_at=item.first_seen_at.isoformat() if item.first_seen_at else None,
            summary_preview=item_dict["summary_preview"],
            reason_labels=[_reason_label(reason) for reason in item_dict["reasons"]],
            compile_basis_label=(
                "已有正文，可进行全文分析"
                if item_dict["compile_basis"] == "fulltext"
                else "基于来源摘要与元数据分析"
            ),
        ))

        if len(results) >= limit:
            break

    return results


def _is_weak_title(title: str | None) -> bool:
    if not title:
        return True
    t = title.strip().lower()
    if len(t) < 5:
        return True
    return t in _WEAK_TITLES


def _reason_label(reason: str) -> str:
    if reason.startswith("topic_match"):
        return "命中关注主题"
    if reason == "rich_metadata":
        return "来源信息较完整"
    if reason == "has_snapshot":
        return "已有正文内容"
    if reason.startswith("source_priority"):
        return "来源优先级较高"
    if reason.startswith("fresh"):
        return "近期新发现"
    if reason == "weak_title":
        return "标题信息较弱"
    return reason


_METADATA_SUMMARY_KEYS = (
    "zh_summary", "summary_zh", "zh_one_liner",
    "summary", "rss_summary", "description",
    "detail_description", "content_snippet",
)


def _build_summary_preview(meta: dict[str, Any] | None) -> str | None:
    """Build a short Chinese summary preview for compile candidates.

    Priority: zh_summary > zh_one_liner > first available metadata summary.
    Returns up to 120 chars, or None if nothing is available.
    """
    if not meta:
        return None
    # Try zh_summary first
    for key in ("zh_summary", "summary_zh"):
        val = meta.get(key)
        if isinstance(val, str) and val.strip():
            text = " ".join(val.strip().split())
            return text[:120] if len(text) > 120 else text
    # Try zh_one_liner
    val = meta.get("zh_one_liner")
    if isinstance(val, str) and val.strip():
        text = " ".join(val.strip().split())
        return text[:120] if len(text) > 120 else text
    # Fallback: first available metadata summary
    for key in ("summary", "rss_summary", "description", "detail_description", "content_snippet"):
        val = meta.get(key)
        if isinstance(val, str) and val.strip() and len(val) >= 30:
            text = " ".join(val.strip().split())
            return text[:120] if len(text) > 120 else text
    return None
