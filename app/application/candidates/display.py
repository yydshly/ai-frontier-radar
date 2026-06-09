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
    """Return True if title is a weak/CTA string (case-insensitive)."""
    if not title or not title.strip():
        return True
    return title.strip().lower() in _WEAK_TITLES


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

    # ── Time label: published_at takes priority over first_seen_at ────────
    time_label: str
    pub_date = _format_date(item.published_at)
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
    summary: str                  # Lightweight summary from metadata
    time_label: str               # "发布于 YYYY-MM-DD" or "发现于 YYYY-MM-DD"
    source_key: str
    status: str
    insight_card_id: int | None
    is_title_weak: bool          # True if original title was a weak CTA string
