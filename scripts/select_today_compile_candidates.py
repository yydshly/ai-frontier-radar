#!/usr/bin/env python3
"""Select today compile candidates for InsightCard generation — V1.0-beta.16 Phase 4.3.

Default dry-run (read-only). Outputs ranked candidates without writing anything.

Usage:
    python scripts/select_today_compile_candidates.py                          # dry-run
    python scripts/select_today_compile_candidates.py --hours 24 --limit 10  # custom
    python scripts/select_today_compile_candidates.py --per-source-limit 3    # per-source cap
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Scoring constants ───────────────────────────────────────────────────────────

# Source priority weights (higher = more important)
_SOURCE_PRIORITY = {
    "openai_news": 10,
    "anthropic_news": 10,
    "deepmind_blog": 8,
    "huggingface_blog": 7,
    "meta_ai_blog": 7,
    "nvidia_ai_blog": 7,
    "microsoft_ai_source": 6,
    "stanford_hai": 5,
    "mit_news_ai": 5,
    "arxiv_cs_ai": 4,
    "arxiv_cs_cl": 3,
    "arxiv_cs_lg": 3,
    "mistral_ai_news": 5,
    "cohere_blog": 5,
    "berkeley_bair_blog": 4,
}

# Keywords that suggest high-value content (in title or URL)
_TOPIC_KEYWORDS = [
    "coding", "codex", "developer", "agent", "workflow", "rag", "retrieval",
    "document", "pdf", "tts", "voice", "audio", "video", "safety", "policy",
    "openai", "anthropic", "deepmind", "gemini", "claude", "minimax",
    "mistral", "cohere", "huggingface", "arxiv",
    "llm", "gpt", "gemini", "claude", "mistral", "benchmark",
    "reasoning", "chain-of-thought", "reasoning", "inference",
    "multimodal", "vision", "image", "video", "audio", "speech",
    "alignment", "rlhf", "fine-tuning", "training",
    "memory", "context", "attention", "transformer",
    "robotics", " embodied", "agent", "planning",
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
class ScoredCandidate:
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


# ── Candidate selection logic ─────────────────────────────────────────────────


def select_candidates(
    db,
    hours: int = 24,
    limit: int = 10,
    per_source_limit: int = 3,
) -> list[ScoredCandidate]:
    """Select and rank top compile candidates. Read-only."""
    from app.models import SourceItem, Source
    from app.application.content.content_snapshot import get_snapshot_path

    cutoff = datetime.utcnow() - timedelta(hours=hours)
    now = datetime.utcnow()

    # Load all sources for enabled check
    enabled_sources = {
        s.id: s.source_key
        for s in db.query(Source).filter(Source.enabled.is_(True)).all()
    }

    # Collect candidates
    all_items = (
        db.query(SourceItem)
        .filter(
            (SourceItem.first_seen_at >= cutoff) | (SourceItem.last_seen_at >= cutoff),
        )
        .all()
    )

    scored: list[tuple[int, dict]] = []  # (score, item_dict)

    for item in all_items:
        # Basic filters
        if item.status not in ("discovered", "fetched"):
            continue
        if item.insight_card_id:
            continue  # already has card
        if not item.title or not item.title.strip():
            continue
        if not item.url or not item.url.strip():
            continue
        if item.source_key in _BLOCKED_SOURCES:
            continue
        if item.source_id not in enabled_sources:
            continue
        # Check blocked domains
        url_lower = item.url.lower()
        if any(b in url_lower for b in _BLOCKED_DOMAINS):
            continue

        # Determine compile basis
        has_snapshot = get_snapshot_path(item.id).exists()
        compile_basis = "fulltext" if has_snapshot else "metadata"

        # Parse raw_metadata
        raw = item.raw_metadata_json
        rich_text = ""
        if raw:
            try:
                meta = json.loads(raw)
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
        src_score = _SOURCE_PRIORITY.get(item.source_key, 0)
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

        # Title quality penalties
        if _is_weak_title(item.title):
            score -= 20
            reasons.append("weak_title")

        # Per-source limit tracking
        item_dict = {
            "item": item,
            "score": score,
            "reasons": reasons,
            "compile_basis": compile_basis,
            "rich_text": rich_text,
        }
        scored.append((score, item_dict))

    # Sort by score descending
    scored.sort(key=lambda x: -x[0])

    # Per-source limit
    source_counts: dict[str, int] = defaultdict(int)
    results: list[ScoredCandidate] = []
    for score, item_dict in scored:
        item: SourceItem = item_dict["item"]
        if source_counts[item.source_key] >= per_source_limit:
            continue
        source_counts[item.source_key] += 1

        results.append(ScoredCandidate(
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


# ── Output formatting ────────────────────────────────────────────────────────────


def format_candidates(candidates: list[ScoredCandidate]) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("Today Compile Candidate Selection (V1.0-beta.16 Phase 4.3)")
    lines.append("=" * 70)
    lines.append(f"  selected_candidates: {len(candidates)}")
    lines.append("")

    if not candidates:
        lines.append("  (no candidates found)")
    else:
        for c in candidates:
            lines.append(f"[{c.rank}] id={c.source_item_id} source_key={c.source_key} score={c.score}")
            lines.append(f"    compile_basis={c.compile_basis} "
                         f"reasons={', '.join(c.reasons) if c.reasons else 'none'}")
            lines.append(f"    title: {c.title[:60]}")
            lines.append(f"    url:   {c.url[:70]}")
            lines.append(f"    first_seen: {c.first_seen_at[:16] if c.first_seen_at else '?'}")
    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Select top compile candidates from today radar (dry-run)."
    )
    parser.add_argument(
        "--hours", type=int, default=24,
        help="Time window in hours (default: 24).",
    )
    parser.add_argument(
        "--limit", type=int, default=10,
        help="Maximum candidates to return (default: 10).",
    )
    parser.add_argument(
        "--per-source-limit", type=int, default=3,
        help="Max candidates per source (default: 3).",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output as JSON instead of human-readable.",
    )
    args = parser.parse_args()

    print("Loading database...")
    try:
        from app.db import SessionLocal, init_db
    except Exception as e:
        print(f"[ERROR] Failed to import app modules: {e}")
        return 1

    init_db()
    db = SessionLocal()

    try:
        candidates = select_candidates(
            db,
            hours=args.hours,
            limit=args.limit,
            per_source_limit=args.per_source_limit,
        )

        if args.json:
            output = [
                {
                    "rank": c.rank,
                    "source_item_id": c.source_item_id,
                    "source_key": c.source_key,
                    "title": c.title,
                    "url": c.url,
                    "score": c.score,
                    "reasons": c.reasons,
                    "compile_basis": c.compile_basis,
                    "published_at": c.published_at,
                    "first_seen_at": c.first_seen_at,
                }
                for c in candidates
            ]
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            print(format_candidates(candidates))

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
