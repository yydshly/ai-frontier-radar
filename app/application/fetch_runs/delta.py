"""Fetch Delta Digest - Application layer for FetchRun delta classification.

This module provides:
- FetchDeltaItem: individual item with delta classification
- FetchDeltaDigest: aggregated digest for a FetchRun
- FetchDeltaDigestService: builds digest from a FetchRun
- extract_lightweight_summary: extracts summary from raw_metadata_json
"""
import json
import re
import html
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models import FetchRun, SourceItem


# Maximum summary length
MAX_SUMMARY_LENGTH = 180

# Time window hours when finished_at is missing
ESTIMATED_WINDOW_HOURS = 2


@dataclass
class FetchDeltaItem:
    """A single SourceItem with delta classification."""
    item_id: int | None
    title: str
    url: str | None
    source_key: str
    published_at: str | None
    summary: str
    status: str
    insight_card_id: int | None
    delta_type: str  # "new" | "seen" | "updated" | "failed"
    # Display-ready fields (populated by _enrich_display)
    display_title: str = ""      # title or "标题待修复" for weak titles
    is_title_weak: bool = False
    raw_title: str | None = None  # original weak title if is_title_weak
    time_label: str = ""          # "发布于 YYYY-MM-DD" or "发现于 YYYY-MM-DD"


@dataclass
class FailedDeltaItem:
    """A failed URL without a SourceItem."""
    url: str
    error: str | None
    source_key: str


@dataclass
class FetchDeltaDigest:
    """Aggregated delta digest for a FetchRun."""
    run_id: int
    new_items: list[FetchDeltaItem] = field(default_factory=list)
    seen_items: list[FetchDeltaItem] = field(default_factory=list)
    updated_items: list[FetchDeltaItem] = field(default_factory=list)
    failed_items: list[FetchDeltaItem] = field(default_factory=list)

    @property
    def new_count(self) -> int:
        return len(self.new_items)

    @property
    def seen_count(self) -> int:
        return len(self.seen_items)

    @property
    def updated_count(self) -> int:
        return len(self.updated_items)

    @property
    def failed_count(self) -> int:
        return len(self.failed_items)

    @property
    def total_count(self) -> int:
        return self.new_count + self.seen_count + self.updated_count + self.failed_count


def extract_lightweight_summary(item: SourceItem) -> str:
    """Extract lightweight summary from SourceItem's raw_metadata_json.

    Priority order:
    1. zh_one_liner
    2. detail_description   (from article detail page og:description etc.)
    3. summary
    4. description
    5. excerpt
    6. content_snippet
    7. og_description
    8. meta_description
    9. rss_summary
    10. rss_description

    Falls back to:
    - "来自 {source_key} 的候选资料：{title}"
    - "来自 {source_key} 的候选资料，暂无摘要。"

    Does NOT call LLM. Limits to 180 chars. Strips HTML tags.
    """
    raw_metadata: dict[str, Any] = {}

    if item.raw_metadata_json:
        try:
            raw_metadata = json.loads(item.raw_metadata_json)
        except (json.JSONDecodeError, TypeError):
            pass

    # Priority-ordered list of summary field names
    summary_fields = [
        "zh_one_liner",
        "detail_description",
        "summary",
        "description",
        "excerpt",
        "content_snippet",
        "og_description",
        "meta_description",
        "rss_summary",
        "rss_description",
    ]

    for field_name in summary_fields:
        value = raw_metadata.get(field_name)
        if value and isinstance(value, str) and value.strip():
            summary = value.strip()
            # Strip HTML tags
            summary = re.sub(r'<[^>]+>', '', summary)
            # Normalize whitespace
            summary = re.sub(r'\s+', ' ', summary)
            # Truncate
            if len(summary) > MAX_SUMMARY_LENGTH:
                summary = summary[:MAX_SUMMARY_LENGTH - 3] + "..."
            return summary

    # Fallback
    if item.title:
        return f"来自 {item.source_key} 的候选资料：{item.title}"

    return f"来自 {item.source_key} 的候选资料，暂无摘要。"


def _get_window_end(run: FetchRun) -> datetime:
    """Get the time window end for a FetchRun.

    If finished_at is available, use it.
    Otherwise use started_at + ESTIMATED_WINDOW_HOURS.
    """
    if run.finished_at:
        return run.finished_at
    if run.started_at:
        return run.started_at + timedelta(hours=ESTIMATED_WINDOW_HOURS)
    # Fallback: now if started_at is also None
    return datetime.utcnow()


def _parse_metadata_json(metadata_json: str | None) -> dict[str, Any]:
    """Parse metadata_json safely, returning empty dict on failure."""
    if not metadata_json:
        return {}
    try:
        return json.loads(metadata_json)
    except (json.JSONDecodeError, TypeError):
        return {}


def _has_update_marker(raw_metadata: dict[str, Any]) -> bool:
    """Check if raw_metadata indicates content was updated."""
    update_markers = ["updated", "changed", "content_hash_changed", "modified"]
    for marker in update_markers:
        if marker in raw_metadata:
            value = raw_metadata.get(marker)
            # Treat falsy values (None, False, 0, "") as no marker
            if value:
                return True
    return False


# Weak/CTA titles — same set as used in html_index_probe.py and candidates/display.py.
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
    """Return True if title is a weak/CTA string (case-insensitive, whitespace-normalized)."""
    if not title or not title.strip():
        return True
    normalized = " ".join(title.strip().split())
    return normalized.lower() in _WEAK_TITLES


def _format_date(value: Any) -> str | None:
    """Format a date/datetime/string to YYYY-MM-DD, or return None."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, str) and value.strip():
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value.strip()[:19], fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
        return value.strip()[:10]
    return None


class FetchDeltaDigestService:
    """Service for building FetchDeltaDigest from a FetchRun."""

    def __init__(self, db: Session):
        self.db = db

    def build_for_run(self, run: FetchRun) -> FetchDeltaDigest:
        """Build delta digest for a FetchRun.

        Classifies items into:
        - new: first_seen_at within run time window
        - seen: first_seen_at before run, last_seen_at within window, no update marker
        - updated: first_seen_at before run, last_seen_at within window, has update marker
        - failed: from run.metadata_json.failed_urls or errors
        """
        digest = FetchDeltaDigest(run_id=run.id)

        if not run.started_at:
            # No start time means no items can be classified
            return digest

        window_end = _get_window_end(run)

        # Build failed items from metadata_json
        failed_urls = self._extract_failed_urls(run)
        for failed_url, error in failed_urls:
            delta_item = FetchDeltaItem(
                item_id=None,
                title=error or "Failed",
                url=failed_url,
                source_key=run.source_key,
                published_at=None,
                summary=error or "抓取失败",
                status="failed",
                insight_card_id=None,
                delta_type="failed",
                # Failed items always get these display defaults
                display_title="抓取失败",
                is_title_weak=False,
                raw_title=None,
                time_label="时间未知",
            )
            digest.failed_items.append(delta_item)

        # Get all source_items for this source_key
        # We need to query more broadly to find seen/updated items
        all_items = (
            self.db.query(SourceItem)
            .filter(SourceItem.source_key == run.source_key)
            .order_by(SourceItem.first_seen_at.desc())
            .limit(500)
            .all()
        )

        for item in all_items:
            if not item.first_seen_at:
                continue

            first_seen = item.first_seen_at
            last_seen = item.last_seen_at

            # Case 1: New item - first_seen within window
            if run.started_at <= first_seen <= window_end:
                digest.new_items.append(self._item_to_delta(item, "new"))

            # Case 2: Seen or Updated - first_seen before window, last_seen within window
            elif first_seen < run.started_at and last_seen and last_seen >= run.started_at and last_seen <= window_end:
                raw_metadata = _parse_metadata_json(item.raw_metadata_json)
                if _has_update_marker(raw_metadata):
                    digest.updated_items.append(self._item_to_delta(item, "updated"))
                else:
                    digest.seen_items.append(self._item_to_delta(item, "seen"))

        return digest

    def _extract_failed_urls(self, run: FetchRun) -> list[tuple[str, str | None]]:
        """Extract failed URLs and errors from run.metadata_json."""
        metadata = _parse_metadata_json(run.metadata_json)
        failed = []

        # Try delta.failed_urls first
        delta = metadata.get("delta", {})
        if isinstance(delta, dict):
            failed_urls_list = delta.get("failed_urls", [])
            if isinstance(failed_urls_list, list):
                for entry in failed_urls_list:
                    if isinstance(entry, dict):
                        url = entry.get("url")
                        error = entry.get("error")
                        if url:
                            failed.append((url, error))
                return failed

        # Try top-level failed_urls
        failed_urls_list = metadata.get("failed_urls", [])
        if isinstance(failed_urls_list, list):
            for entry in failed_urls_list:
                if isinstance(entry, dict):
                    url = entry.get("url")
                    error = entry.get("error")
                    if url:
                        failed.append((url, error))
                elif isinstance(entry, str):
                    failed.append((entry, None))

        # Try errors array
        errors = metadata.get("errors", [])
        if isinstance(errors, list):
            for entry in errors:
                if isinstance(entry, dict):
                    url = entry.get("url")
                    error = entry.get("error")
                    if url:
                        failed.append((url, error))

        return failed

    def _item_to_delta(self, item: SourceItem, delta_type: str) -> FetchDeltaItem:
        """Convert a SourceItem to FetchDeltaItem with display enrichment."""
        delta_item = FetchDeltaItem(
            item_id=item.id,
            title=item.title or "无标题",
            url=item.url,
            source_key=item.source_key,
            published_at=item.published_at,
            summary=extract_lightweight_summary(item),
            status=item.status,
            insight_card_id=item.insight_card_id,
            delta_type=delta_type,
        )
        self._enrich_display(delta_item, item)
        return delta_item

    def _enrich_display(self, delta_item: FetchDeltaItem, item: SourceItem) -> None:
        """Populate display_title, is_title_weak, raw_title, time_label on delta_item."""
        title = delta_item.title
        is_weak = _is_weak_title(title)
        delta_item.is_title_weak = is_weak
        delta_item.raw_title = title if is_weak else None
        delta_item.display_title = "标题待修复" if is_weak else title

        # time_label: published_at > metadata > first_seen_at
        pub_date = _format_date(item.published_at)
        if not pub_date:
            raw_meta = _parse_metadata_json(item.raw_metadata_json)
            for meta_key in ("published_at", "article_published_time", "date", "pub_date"):
                pub_date = _format_date(raw_meta.get(meta_key))
                if pub_date:
                    break
        if pub_date:
            delta_item.time_label = f"发布于 {pub_date}"
        elif item.first_seen_at:
            delta_item.time_label = f"发现于 {_format_date(item.first_seen_at)}"
        else:
            delta_item.time_label = "时间未知"

        # Weak title summary protection: if title is weak and summary contains it, replace
        if is_weak and title and title in delta_item.summary:
            delta_item.summary = "暂无摘要。请重新探测该来源或运行标题修复脚本。"
