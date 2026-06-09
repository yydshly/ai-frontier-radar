"""Candidate display card builder — transforms SourceItems into display-ready cards.

Does NOT call LLM. Does NOT modify database state.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Union

from app.models import SourceItem
from app.application.fetch_runs.delta import extract_lightweight_summary


# Weak/CTA titles — must match the set used in html_index_probe.py.
# These titles come from list-page CTA text, not real article titles.
_WEAK_TITLES = frozenset(
    w.lower() for w in (
        "featured",
        "learn more",
        "read more",
        "more",
        "view",
        "explore",
        "see more",
        "continue reading",
        "details",
    )
)


def _is_weak_title(title: str | None) -> bool:
    """Return True if title is a weak/CTA string (case-insensitive, whitespace-normalized).

    Normalizes internal whitespace (tabs, newlines, multiple spaces) before
    comparison so "Learn\\nMore", "LEARN   MORE", etc. are detected.
    """
    if not title or not title.strip():
        return True
    # Collapse all runs of whitespace to a single space
    normalized = " ".join(title.strip().split())
    return normalized.lower() in _WEAK_TITLES


def _format_date(value: Any) -> str | None:
    """Format a date/datetime/string to YYYY-MM-DD, or return None."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, str) and value.strip():
        # Try parsing ISO date strings
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value.strip()[:19], fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
        # Return as-is if parsing fails
        return value.strip()[:10]
    return None


def build_candidate_display_card(item: SourceItem) -> "CandidateDisplayCard":
    """Build a CandidateDisplayCard from a SourceItem.

    The returned dataclass is display-only — it reflects current DB state
    without modifying it.
    """
    title = item.title or ""

    # ── Title display logic ────────────────────────────────────────────────
    is_title_weak = _is_weak_title(title)
    raw_title = title if is_title_weak else None

    if is_title_weak:
        display_title = "标题待修复"
    else:
        display_title = title

    # ── Summary ───────────────────────────────────────────────────────────
    summary = extract_lightweight_summary(item)
    # If title is weak and the summary contains it, the fallback fired.
    # Replace with a neutral message so weak CTA text never surfaces in summary.
    if is_title_weak and title and title in summary:
        summary = "暂无摘要。请重新探测该来源或运行标题修复脚本。"

    # ── Detail summary (for reading panel): zh_summary > zh_one_liner > fallback chain ──
    raw_meta: dict[str, Any] = {}
    if item.raw_metadata_json:
        try:
            import json as _json
            raw_meta = _json.loads(item.raw_metadata_json)
        except Exception:
            pass

    detail_summary: str | None = raw_meta.get("zh_summary")
    if not detail_summary:
        # Fallback: zh_one_liner (for items generated before zh_summary existed)
        detail_summary = raw_meta.get("zh_one_liner")
    if not detail_summary:
        # Final fallback: the existing summary chain
        detail_summary = raw_meta.get(
            "detail_description"
        ) or raw_meta.get("summary") or raw_meta.get("description") or raw_meta.get(
            "excerpt"
        ) or raw_meta.get(
            "content_snippet"
        ) or raw_meta.get(
            "og_description"
        ) or raw_meta.get(
            "meta_description"
        ) or raw_meta.get(
            "rss_summary"
        ) or raw_meta.get("rss_description")

    # Strip HTML and normalize whitespace for detail_summary
    if detail_summary:
        import re as _re
        detail_summary = _re.sub(r"<[^>]+>", "", detail_summary)
        detail_summary = " ".join(detail_summary.strip().split())
        if len(detail_summary) > 260:
            detail_summary = detail_summary[:257] + "..."
    else:
        detail_summary = None

    # ── Time label: item.published_at > metadata > first_seen_at ─────────────
    time_label: str
    pub_date = _format_date(item.published_at)
    if not pub_date:
        for meta_key in ("published_at", "article_published_time", "date", "pub_date"):
            pub_date = _format_date(raw_meta.get(meta_key))
            if pub_date:
                break
    if pub_date:
        time_label = f"发布于 {pub_date}"
    elif item.first_seen_at:
        time_label = f"发现于 {_format_date(item.first_seen_at)}"
    else:
        time_label = "时间未知"

    # ── URL (prefer canonical_url if set) ────────────────────────────────
    url = item.canonical_url or item.url

    return CandidateDisplayCard(
        item_id=item.id,
        title=display_title,
        raw_title=raw_title,
        url=url,
        summary=summary,
        detail_summary=detail_summary,
        time_label=time_label,
        source_key=item.source_key,
        status=item.status,
        insight_card_id=item.insight_card_id,
        is_title_weak=is_title_weak,
    )


@dataclass
class CandidateDisplayCard:
    """Display-ready card for the candidate pool UI.

    All fields are derived from SourceItem without modifying database state.
    """
    item_id: int
    title: str                    # Display title (weak → "标题待修复")
    raw_title: str | None        # Original weak title if title is weak, else None
    url: str | None
    summary: str                  # Lightweight summary from metadata (zh_one_liner for list view)
    detail_summary: str | None   # Longer summary for reading panel (zh_summary or fallback)
    time_label: str               # "发布于 YYYY-MM-DD" or "发现于 YYYY-MM-DD"
    source_key: str
    status: str
    insight_card_id: int | None
    is_title_weak: bool          # True if original title was a weak CTA string
