"""RadarTodayService — builds the "today's AI frontier radar" reading view.

Read-only view layer:
- Queries recent SourceItems (last `hours`, fallback to recent `limit`).
- Reuses build_candidate_display_card() for all display data
  (title / summary / time_label) — never re-implements summary or
  weak-title logic.
- Groups items into a fixed catalog of sections using rule-based
  keyword matching ONLY. Does NOT call any LLM.
- Sorts items using _radar_sort_key to handle mixed datetime formats
  (ISO, RFC822, datetime objects) correctly.

Does NOT modify database state. Does NOT trigger fetching or compilation.
"""
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from app.models import SourceItem
from app.application.candidates.display import (
    CandidateDisplayCard,
    build_candidate_display_card,
)


# ── Query bounds ───────────────────────────────────────────────────────────
DEFAULT_HOURS = 24
DEFAULT_LIMIT = 50
MIN_HOURS, MAX_HOURS = 1, 168
MIN_LIMIT, MAX_LIMIT = 1, 100
DEFAULT_PER_PAGE = 20
MIN_PER_PAGE, MAX_PER_PAGE = 5, 50

# Number of newest items pinned into the "today focus" section.
TODAY_FOCUS_SIZE = 5


# ── Catalog definition ───────────────────────────────────────────────────────
# Order matters: a normal item is placed in the FIRST matching category.
# today_focus is special (newest N items) and handled separately.
@dataclass(frozen=True)
class _CategoryDef:
    key: str
    title: str
    keywords: tuple[str, ...]


TODAY_FOCUS_KEY = "today_focus"
TODAY_FOCUS_TITLE = "今日重点"
OTHERS_KEY = "others"
OTHERS_TITLE = "其他"

# Keyword categories evaluated in order. Keywords are matched as lowercase
# substrings against a text blob built from source_key/title/summary/metadata.
_CATEGORIES: tuple[_CategoryDef, ...] = (
    _CategoryDef(
        "ai_coding",
        "AI 编程工具",
        ("codex", "coding", "code", "developer", "cursor", "programming",
         "software engineer", "copilot", "ide"),
    ),
    _CategoryDef(
        "agent_rag",
        "Agent / RAG / 文档理解",
        ("agent", "multi-agent", "rag", "retrieval", "document", "knowledge",
         "workflow"),
    ),
    _CategoryDef(
        "model_company",
        "模型公司动态",
        ("openai", "anthropic", "deepmind", "mistral", "cohere", "meta",
         "microsoft", "nvidia", "huggingface", "hugging face", "google",
         "claude", "gpt", "gemini", "llama"),
    ),
    _CategoryDef(
        "multimodal_voice_video",
        "多模态 / 语音 / 视频",
        ("voice", "audio", "tts", "speech", "video", "image", "multimodal",
         "vision"),
    ),
    _CategoryDef(
        "safety_policy",
        "AI 安全 / 政策",
        ("safety", "policy", "regulation", "risk", "eval", "alignment",
         "security"),
    ),
)

# Stable order of sections as shown in the sidebar / main area.
SECTION_ORDER: tuple[tuple[str, str], ...] = (
    (TODAY_FOCUS_KEY, TODAY_FOCUS_TITLE),
    *((c.key, c.title) for c in _CATEGORIES),
    (OTHERS_KEY, OTHERS_TITLE),
)


@dataclass
class RadarTodaySection:
    key: str
    title: str
    items: list = field(default_factory=list)


@dataclass
class RadarTodayView:
    total_items: int
    selected_item_id: int | None
    selected_item: object | None
    sections: list  # list[RadarTodaySection]
    display_map: dict  # dict[int, CandidateDisplayCard]
    fallback_used: bool
    hours: int
    limit: int
    # True when item_id was supplied but no matching SourceItem exists.
    selected_missing: bool = False
    # ── Pagination (over the sorted candidate set) ──────────────────────────
    page: int = 1
    per_page: int = DEFAULT_PER_PAGE
    total_pages: int = 1
    has_prev: bool = False
    has_next: bool = False


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _to_naive_utc(value: datetime) -> datetime:
    """Strip timezone info and return a naive UTC datetime.

    Converts aware datetimes to UTC, then removes tzinfo.
    Leaves naive datetimes unchanged.
    """
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _radar_sort_key(item: SourceItem) -> datetime:
    """Return a naive UTC datetime used for display-layer sorting of a SourceItem.

    Priority:
    1. published_at — parsed if it is a datetime object, an ISO string,
       or an RFC822 string (e.g. "Wed, 27 May 2026 10:00:00 GMT").
    2. last_seen_at — used as-is.
    3. first_seen_at — used as-is.
    4. datetime.min — used when nothing is available.

    All returned datetimes are naive (timezone-stripped) to allow safe sorting.
    Bad strings fall through to datetime.min without raising.
    """
    # 1. published_at
    pub = item.published_at
    if pub is not None:
        if isinstance(pub, datetime):
            return _to_naive_utc(pub)
        if isinstance(pub, str) and pub.strip():
            try:
                # RFC822 / asctime format (email standard) — always aware UTC
                return _to_naive_utc(parsedate_to_datetime(pub))
            except (ValueError, TypeError):
                pass
            try:
                # ISO 8601 format — may be aware or naive
                return _to_naive_utc(datetime.fromisoformat(pub.strip()))
            except (ValueError, TypeError):
                pass
        # Unusable (empty string, etc.) → fall through

    # 2. last_seen_at
    if item.last_seen_at is not None:
        return _to_naive_utc(item.last_seen_at)

    # 3. first_seen_at
    if item.first_seen_at is not None:
        return _to_naive_utc(item.first_seen_at)

    # 4. Nothing usable
    return datetime.min


def _classify_blob(item: SourceItem, card: CandidateDisplayCard) -> str:
    """Build a lowercase text blob used for keyword classification.

    Combines source_key, title, the display summary, and selected
    raw_metadata_json fields (detail_description / rss_summary /
    description / tags).
    """
    parts: list[str] = [
        item.source_key or "",
        item.title or "",
        card.summary or "",
    ]

    if item.raw_metadata_json:
        try:
            meta: dict[str, Any] = json.loads(item.raw_metadata_json)
        except (json.JSONDecodeError, TypeError):
            meta = {}
        for key in ("detail_description", "rss_summary", "description"):
            value = meta.get(key)
            if isinstance(value, str):
                parts.append(value)
        tags = meta.get("tags")
        if isinstance(tags, list):
            parts.extend(str(t) for t in tags)
        elif isinstance(tags, str):
            parts.append(tags)

    return " ".join(parts).lower()


def _category_for(blob: str) -> str:
    """Return the first matching category key, or OTHERS_KEY."""
    for category in _CATEGORIES:
        for keyword in category.keywords:
            if keyword in blob:
                return category.key
    return OTHERS_KEY


class RadarTodayService:
    """Builds a RadarTodayView from recent SourceItems."""

    def __init__(self, db: Session):
        self.db = db

    def build_today_view(
        self,
        selected_item_id: int | None = None,
        hours: int = DEFAULT_HOURS,
        limit: int = DEFAULT_LIMIT,
        page: int = 1,
        per_page: int = DEFAULT_PER_PAGE,
    ) -> RadarTodayView:
        hours = _clamp(int(hours), MIN_HOURS, MAX_HOURS)
        limit = _clamp(int(limit), MIN_LIMIT, MAX_LIMIT)
        per_page = _clamp(int(per_page), MIN_PER_PAGE, MAX_PER_PAGE)
        page = max(1, int(page))

        order = desc(func.coalesce(
            SourceItem.published_at,
            SourceItem.last_seen_at,
            SourceItem.first_seen_at,
        ))

        # ── Recent-window query ──────────────────────────────────────────
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        items = (
            self.db.query(SourceItem)
            .filter(
                or_(
                    SourceItem.first_seen_at >= cutoff,
                    SourceItem.last_seen_at >= cutoff,
                )
            )
            .order_by(order)
            .limit(limit)
            .all()
        )

        # ── Fallback: most recent `limit` items if window is empty ────────
        fallback_used = False
        if not items:
            fallback_used = True
            items = (
                self.db.query(SourceItem)
                .order_by(order)
                .limit(limit)
                .all()
            )

        # ── Re-sort by display-layer datetime (handles mixed ISO/RFC822) ──
        items = sorted(items, key=_radar_sort_key, reverse=True)

        # ── Pagination over the sorted candidate set ──────────────────────
        total_items = len(items)
        total_pages = max(1, math.ceil(total_items / per_page)) if total_items else 1
        page = min(page, total_pages)  # clamp into valid range
        start = (page - 1) * per_page
        page_items = items[start:start + per_page]
        has_prev = page > 1
        has_next = page < total_pages

        # ── Display cards — only for the current page items ───────────────
        display_map: dict[int, CandidateDisplayCard] = {
            item.id: build_candidate_display_card(item) for item in page_items
        }

        # ── Section grouping (current page only) ──────────────────────────
        sections = self._build_sections(page_items, display_map)

        # ── Selected item resolution ──────────────────────────────────────
        selected_item, selected_missing = self._resolve_selected(
            selected_item_id, page_items, display_map
        )

        return RadarTodayView(
            total_items=total_items,
            selected_item_id=selected_item_id,
            selected_item=selected_item,
            sections=sections,
            display_map=display_map,
            fallback_used=fallback_used,
            hours=hours,
            limit=limit,
            selected_missing=selected_missing,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            has_prev=has_prev,
            has_next=has_next,
        )

    def _build_sections(
        self,
        items: list,
        display_map: dict,
    ) -> list:
        buckets: dict[str, list] = {key: [] for key, _ in SECTION_ORDER}

        # today_focus: the newest TODAY_FOCUS_SIZE items (items already sorted).
        today_focus_ids = {item.id for item in items[:TODAY_FOCUS_SIZE]}
        for item in items[:TODAY_FOCUS_SIZE]:
            buckets[TODAY_FOCUS_KEY].append(item)

        # Normal categories: exclude today_focus items, first matching category only.
        for item in items[TODAY_FOCUS_SIZE:]:
            card = display_map.get(item.id)
            blob = _classify_blob(item, card) if card else (item.source_key or "").lower()
            buckets[_category_for(blob)].append(item)

        return [
            RadarTodaySection(key=key, title=title, items=buckets[key])
            for key, title in SECTION_ORDER
        ]

    def _resolve_selected(
        self,
        selected_item_id: int | None,
        items: list,
        display_map: dict,
    ):
        """Return (selected_item, selected_missing).

        Rules:
        - item_id in current list → that item.
        - item_id not in list but exists in DB → load it (and add a
          display card so the panel can render).
        - item_id supplied but not in DB → (None, missing=True).
        - no item_id → first item, or None if list empty.
        """
        if selected_item_id is None:
            return (items[0] if items else None), False

        for item in items:
            if item.id == selected_item_id:
                return item, False

        # Not in the current window — try the DB directly.
        item = (
            self.db.query(SourceItem)
            .filter(SourceItem.id == selected_item_id)
            .first()
        )
        if item is None:
            return None, True

        if item.id not in display_map:
            display_map[item.id] = build_candidate_display_card(item)
        return item, False
