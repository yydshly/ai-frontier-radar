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
ALL_KEY = "all"
ALL_TITLE = "全部"

# Keyword categories evaluated in order. Keywords are matched as lowercase
# substrings against a text blob built from source_key/title/summary/metadata.
# Order matters: "AI 编程" must come before "模型公司" so that a Codex article
# tagged with "openai" still gets classified as coding. "Agent 工作流" must
# come before "产品机会 / 商业化" so enterprise/workflow items don't drown
# out core agent news.
_CATEGORIES: tuple[_CategoryDef, ...] = (
    _CategoryDef(
        "ai_coding",
        "AI 编程 / 开发者工具",
        (
            "codex", "coding", "code", "developer", "cursor", "copilot",
            "ide", "software engineer", "programming", "devtool",
            "github", "git", "pull request", "cli",
        ),
    ),
    _CategoryDef(
        "agent_workflow",
        "Agent 工作流",
        (
            "agent", "agents", "multi-agent", "workflow", "tool use",
            "computer use", "automation", "autonomous", "orchestration",
        ),
    ),
    _CategoryDef(
        "rag_knowledge",
        "RAG / 知识库",
        (
            "rag", "retrieval", "knowledge base", "vector", "embedding",
            "search", "index", "semantic search", "memory",
        ),
    ),
    _CategoryDef(
        "doc_understanding",
        "文档理解 / 资料处理",
        (
            "document", "pdf", "report", "paper", "reading", "extract",
            "extraction", "ocr", "parser", "markdown", "dataset",
        ),
    ),
    _CategoryDef(
        "model_release",
        "模型公司 / 发布动态",
        (
            "openai", "anthropic", "deepmind", "google", "mistral",
            "cohere", "meta", "microsoft", "nvidia", "huggingface",
            "hugging face", "claude", "gpt", "gemini", "llama",
            "model release", "launches", "announces",
        ),
    ),
    _CategoryDef(
        "open_model_benchmark",
        "开源模型 / Benchmark",
        (
            "open source", "open-weight", "benchmark", "leaderboard",
            "eval", "evaluation", "mmlu", "swe-bench", "arena",
            "performance", "reasoning model",
        ),
    ),
    _CategoryDef(
        "multimodal_video_image",
        "多模态 / 图像 / 视频",
        (
            "multimodal", "vision", "image", "video", "sora", "veo",
            "generate images", "image generation", "video generation",
        ),
    ),
    _CategoryDef(
        "voice_audio",
        "语音 / TTS / 音频",
        (
            "voice", "audio", "tts", "speech", "speech-to-text",
            "text-to-speech", "music", "sound", "transcription",
        ),
    ),
    _CategoryDef(
        "safety_policy",
        "AI 安全 / 政策",
        (
            "safety", "policy", "regulation", "risk", "alignment",
            "security", "governance", "standard", "youth", "privacy",
        ),
    ),
    _CategoryDef(
        "product_business",
        "产品机会 / 商业化",
        (
            "enterprise", "business", "startup", "product", "pricing",
            "revenue", "market", "customer", "use case",
            "case study", "adoption",
        ),
    ),
    _CategoryDef(
        "infra_compute",
        "基础设施 / 算力",
        (
            "infrastructure", "compute", "gpu", "datacenter", "data center",
            "cluster", "training", "inference", "chip", "server",
            "stargate",
        ),
    ),
)

# Stable order of sections as shown in the sidebar / main area.
# "all" is a virtual section; rendered specially by the template.
SECTION_ORDER: tuple[tuple[str, str], ...] = (
    (TODAY_FOCUS_KEY, TODAY_FOCUS_TITLE),
    *((c.key, c.title) for c in _CATEGORIES),
    (OTHERS_KEY, OTHERS_TITLE),
)

# Section keys that are always shown in the sidebar (even if empty).
ALWAYS_VISIBLE_SECTIONS: frozenset[str] = frozenset({TODAY_FOCUS_KEY})


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
    # ── Active sidebar section (default: ALL_KEY) ───────────────────────────
    active_section: str = ALL_KEY
    # ── Per-section item counts over the FULL result set (not current page) ─
    section_counts: dict = field(default_factory=dict)


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
    raw_metadata_json fields (zh_one_liner / zh_summary / detail_description
    / rss_summary / description / summary / tags).

    Including the generated Chinese summary fields ensures the classifier
    can use them once `generate_one_liners.py` populates them — without
    this, a Chinese-summarized item would still classify on English title
    only.
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
        for key in (
            "zh_one_liner", "zh_summary",
            "detail_description", "rss_summary", "description", "summary",
        ):
            value = meta.get(key)
            if isinstance(value, str):
                parts.append(value)
        tags = meta.get("tags")
        if isinstance(tags, list):
            parts.extend(str(t) for t in tags)
        elif isinstance(tags, str):
            parts.append(tags)

    return " ".join(parts).lower()


def _categorize_item(item: SourceItem, card: CandidateDisplayCard | None) -> str:
    """Return the section key for an item, or OTHERS_KEY if no match."""
    if card is None:
        return OTHERS_KEY
    return _category_for(_classify_blob(item, card))


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
        section: str = ALL_KEY,
    ) -> RadarTodayView:
        hours = _clamp(int(hours), MIN_HOURS, MAX_HOURS)
        limit = _clamp(int(limit), MIN_LIMIT, MAX_LIMIT)
        per_page = _clamp(int(per_page), MIN_PER_PAGE, MAX_PER_PAGE)
        page = max(1, int(page))

        # Validate section against known keys (unknown → ALL_KEY).
        valid_keys = {key for key, _ in SECTION_ORDER} | {ALL_KEY}
        if section not in valid_keys:
            section = ALL_KEY

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

        # ── Build display cards for the FULL result set (not just page) ──
        # This is needed to compute per-section counts over the full set
        # and to keep the right-side reading panel rendering consistent
        # when an item_id is selected.
        full_display_map: dict[int, CandidateDisplayCard] = {
            item.id: build_candidate_display_card(item) for item in items
        }

        # ── Per-section counts over the FULL result set ──────────────────
        section_counts: dict[str, int] = {key: 0 for key, _ in SECTION_ORDER}
        section_counts[TODAY_FOCUS_KEY] = min(len(items), TODAY_FOCUS_SIZE)
        for item in items[TODAY_FOCUS_SIZE:]:
            key = _categorize_item(item, full_display_map.get(item.id))
            section_counts[key] = section_counts.get(key, 0) + 1
        # "all" count is the total items in the candidate set.
        section_counts[ALL_KEY] = len(items)

        # ── Filter items to the active section ───────────────────────────
        if section == ALL_KEY:
            filtered_items = items
        elif section == TODAY_FOCUS_KEY:
            filtered_items = items[:TODAY_FOCUS_SIZE]
        else:
            filtered_items = [
                item for item in items[TODAY_FOCUS_SIZE:]
                if _categorize_item(item, full_display_map.get(item.id)) == section
            ]
            # today_focus items are also relevant when section=ALL; for a
            # specific category we only show items in that category, which
            # excludes today_focus by design.

        # ── Pagination over the section-filtered set ──────────────────────
        total_items_in_section = len(filtered_items)
        total_pages = max(1, math.ceil(total_items_in_section / per_page)) if total_items_in_section else 1
        page = min(page, total_pages)  # clamp into valid range
        start = (page - 1) * per_page
        page_items = filtered_items[start:start + per_page]
        has_prev = page > 1
        has_next = page < total_pages

        # ── Display cards — only for the current page items ───────────────
        display_map: dict[int, CandidateDisplayCard] = {
            item.id: full_display_map[item.id] for item in page_items
        }

        # ── Section grouping (current page only, all categories) ─────────
        # We always build the full SECTION_ORDER list so the sidebar can
        # show every category with its full-set count, even if the current
        # page has 0 items in a category.
        full_buckets: dict[str, list] = {key: [] for key, _ in SECTION_ORDER}
        today_focus_ids = {i.id for i in items[:TODAY_FOCUS_SIZE]}
        for item in page_items:
            if item.id in today_focus_ids and section in (ALL_KEY, TODAY_FOCUS_KEY):
                full_buckets[TODAY_FOCUS_KEY].append(item)
            else:
                key = _categorize_item(item, full_display_map.get(item.id))
                full_buckets[key].append(item)
        sections = [
            RadarTodaySection(key=key, title=title, items=full_buckets[key])
            for key, title in SECTION_ORDER
        ]

        # ── Selected item resolution ──────────────────────────────────────
        # Selected item should always be in full_display_map (so panel renders).
        selected_item, selected_missing = self._resolve_selected(
            selected_item_id, page_items, full_display_map
        )
        if selected_item is not None and selected_item.id in full_display_map:
            display_map[selected_item.id] = full_display_map[selected_item.id]

        return RadarTodayView(
            total_items=total_items_in_section,
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
            active_section=section,
            section_counts=section_counts,
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
