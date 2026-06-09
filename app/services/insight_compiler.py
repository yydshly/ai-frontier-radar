"""InsightCard compilation orchestrator."""
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import InsightCard, CardStatus, SourceType, SourceItem
from app.services.fetcher import fetch_url
from app.services.extractor import extract_content
from app.services.cleaner import clean_text
from app.services.deduper import compute_content_hash, check_duplicate
from app.llm.factory import create_llm_client
from app.prompts.insight_card import INSIGHT_SYSTEM_PROMPT, build_insight_user_prompt
from app.services.relevance import get_user_directions
from app.config import MAX_LLM_INPUT_CHARS
from app.logging_config import get_logger

logger = get_logger(__name__)


# ── SourceItem snapshot compilation ──────────────────────────────────────────
# When a SourceItem already carries RSS / metadata (title, summaries, tags),
# we compile a lightweight InsightCard from that snapshot instead of re-fetching
# the original URL (which may 403). Full-text fetch is only a fallback.
SNAPSHOT_MIN_CHARS = 120     # min CONTENT chars to consider a snapshot sufficient
SNAPSHOT_MAX_CHARS = 8000    # hard cap on snapshot text length

# Marker prepended to snapshot-based output so the basis is always visible.
SNAPSHOT_BASIS_NOTE = "【基于来源摘要 / RSS metadata 生成，非全文解析】"
SNAPSHOT_RISK_NOTE = "全文未抓取，判断可能不完整，结论基于公开摘要 / 来源 metadata，建议打开原文核验。"

# Weak/CTA titles — same set used in candidates/display.py and delta.py.
_WEAK_TITLES = frozenset(
    w.lower() for w in (
        "featured", "learn more", "read more", "more", "view",
        "explore", "see more", "continue reading", "details",
    )
)

# raw_metadata_json summary fields, in descending preference order.
_SNAPSHOT_SUMMARY_FIELDS = (
    ("中文一句话摘要", "zh_one_liner"),
    ("中文摘要", "zh_summary"),
    ("详情描述", "detail_description"),
    ("摘要", "summary"),
    ("描述", "description"),
    ("摘录", "excerpt"),
    ("内容片段", "content_snippet"),
    ("OG 描述", "og_description"),
    ("Meta 描述", "meta_description"),
    ("RSS 摘要", "rss_summary"),
    ("RSS 描述", "rss_description"),
)


class CompilationError(Exception):
    """Raised when compilation fails at any step."""
    pass


def _is_weak_title(title: str | None) -> bool:
    """Return True if title is a weak/CTA string (e.g. 'Learn More', 'FEATURED')."""
    if not title or not title.strip():
        return True
    return " ".join(title.strip().split()).lower() in _WEAK_TITLES


def _parse_raw_metadata(item: SourceItem) -> dict:
    """Parse item.raw_metadata_json safely — bad JSON returns {}."""
    if not item.raw_metadata_json:
        return {}
    try:
        parsed = json.loads(item.raw_metadata_json)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def _snapshot_content_chars(item: SourceItem, raw: dict) -> int:
    """Measure the real *content* length (title + summaries), excluding boilerplate.

    Used to decide whether a snapshot is rich enough to compile from directly.
    """
    parts: list[str] = []
    if item.title and not _is_weak_title(item.title):
        parts.append(item.title.strip())
    for _label, key in _SNAPSHOT_SUMMARY_FIELDS:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return len(" ".join(parts))


def build_source_item_snapshot_text(item: SourceItem) -> str:
    """Build a compile-ready snapshot text from a SourceItem's stored metadata.

    Does NOT fetch the URL. Robust against bad/empty raw_metadata_json and
    skips empty fields. Weak/CTA titles are NOT used as the main title.
    Output is capped at SNAPSHOT_MAX_CHARS.
    """
    raw = _parse_raw_metadata(item)
    lines: list[str] = ["资料来源类型：RSS / SourceItem metadata"]

    if item.source_key:
        lines.append(f"来源 Key：{item.source_key}")
    if item.url:
        lines.append(f"原文链接：{item.url}")

    pub = item.published_at or raw.get("published_at")
    if pub:
        lines.append(f"发布时间：{pub}")
    elif item.first_seen_at:
        lines.append(f"首次发现时间：{item.first_seen_at}")
    if item.last_seen_at:
        lines.append(f"最近发现时间：{item.last_seen_at}")

    if item.title and not _is_weak_title(item.title):
        lines.append(f"英文标题：{item.title.strip()}")

    for label, key in _SNAPSHOT_SUMMARY_FIELDS:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(f"{label}：{value.strip()}")

    tags = raw.get("tags")
    if isinstance(tags, list) and tags:
        lines.append("标签：" + ", ".join(str(t) for t in tags if str(t).strip()))
    elif isinstance(tags, str) and tags.strip():
        lines.append(f"标签：{tags.strip()}")

    category = raw.get("category")
    if isinstance(category, str) and category.strip():
        lines.append(f"分类：{category.strip()}")

    text = "\n".join(lines)
    if len(text) > SNAPSHOT_MAX_CHARS:
        text = text[:SNAPSHOT_MAX_CHARS]
    return text


def snapshot_is_sufficient(item: SourceItem) -> bool:
    """Return True if the SourceItem has enough content to compile from metadata."""
    raw = _parse_raw_metadata(item)
    return _snapshot_content_chars(item, raw) >= SNAPSHOT_MIN_CHARS


def compile_url(db: Session, url: str) -> InsightCard:
    """
    Full pipeline: fetch URL -> extract content -> clean -> deduplicate -> call LLM -> save card.

    Returns:
        The created or existing InsightCard (never raises, always returns a card)
    """
    logger.info(f"Starting compilation for URL: {url}")

    # Initialize variables to track partial state for failed card creation
    content_hash = ""
    cleaned_text = ""
    source_type = SourceType.UNKNOWN

    # Step 1: Fetch URL
    try:
        content, content_type = fetch_url(url)
    except Exception as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return _create_failed_card(db, url, SourceType.UNKNOWN, "", "", f"URL fetch failed: {e}")

    # Step 2: Extract content
    try:
        text, title, author, source_type = extract_content(url, content, content_type)
    except Exception as e:
        logger.error(f"Failed to extract content from {url}: {e}")
        return _create_failed_card(db, url, SourceType.UNKNOWN, "", "", f"Content extraction failed: {e}")

    if not text or len(text) < 100:
        msg = f"Extracted text too short ({len(text)} chars), likely extraction failure"
        logger.error(msg)
        return _create_failed_card(db, url, source_type, "", "", msg)

    # Step 3: Clean text
    try:
        cleaned_text = clean_text(text)
    except Exception as e:
        logger.error(f"Failed to clean text: {e}")
        return _create_failed_card(db, url, source_type, "", "", f"Text cleaning failed: {e}")

    # Step 4: Compute hash and check for duplicates
    try:
        content_hash = compute_content_hash(cleaned_text)
    except Exception as e:
        logger.error(f"Failed to compute content hash: {e}")
        return _create_failed_card(db, url, source_type, cleaned_text, "", f"Hash computation failed: {e}")

    try:
        existing = check_duplicate(db, url, content_hash)
        if existing:
            logger.info(f"Duplicate found: existing card {existing.id}")
            return existing
    except Exception as e:
        logger.error(f"Failed to check duplicate: {e}")
        # Non-fatal, continue

    # Step 5: Create LLM client and call it
    try:
        client = create_llm_client()
    except ValueError as e:
        # API key missing or profile error - create failed card
        logger.error(f"LLM config error: {e}")
        return _create_failed_card(db, url, source_type, cleaned_text, content_hash, str(e))
    except Exception as e:
        logger.error(f"Failed to create LLM client: {e}")
        return _create_failed_card(db, url, source_type, cleaned_text, content_hash, f"LLM client init failed: {e}")

    try:
        llm_result = client.generate_json(
            system_prompt=INSIGHT_SYSTEM_PROMPT,
            user_prompt=build_insight_user_prompt(
                source_content=cleaned_text,
                user_directions=get_user_directions(),
                max_chars=MAX_LLM_INPUT_CHARS,
            ),
        )
    except Exception as e:
        logger.error(f"LLM call failed for {url}: {e}")
        return _create_failed_card(db, url, source_type, cleaned_text, content_hash, f"LLM call failed: {e}")

    # Step 6: Build and save card
    card = InsightCard(
        source_url=url,
        source_type=source_type,
        source_title=llm_result.get("source_title") or title,
        source_author=llm_result.get("source_author") or author,
        source_published_at=llm_result.get("source_published_at"),
        content_hash=content_hash,
        cleaned_text_preview=cleaned_text[:1000] if len(cleaned_text) > 1000 else cleaned_text,
        status=CardStatus.COMPLETED,
        error_message=None,
        summary_zh=llm_result.get("summary_zh"),
        key_points_zh=json.dumps(llm_result.get("key_points_zh") or [], ensure_ascii=False),
        technical_insights_zh=json.dumps(llm_result.get("technical_insights_zh") or [], ensure_ascii=False),
        product_opportunities_zh=json.dumps(llm_result.get("product_opportunities_zh") or [], ensure_ascii=False),
        risks_zh=json.dumps(llm_result.get("risks_zh") or [], ensure_ascii=False),
        action_items_zh=json.dumps(llm_result.get("action_items_zh") or [], ensure_ascii=False),
        relevance_score=llm_result.get("relevance_score") or 0,
        relevance_reasons_zh=json.dumps(llm_result.get("relevance_reasons_zh") or [], ensure_ascii=False),
        related_user_directions=json.dumps(llm_result.get("related_user_directions") or [], ensure_ascii=False),
        model_name=llm_result.get("model_name"),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    db.add(card)
    db.commit()
    db.refresh(card)

    logger.info(f"Created InsightCard {card.id} for {url}")
    return card


def compile_source_item_snapshot(db: Session, item: SourceItem) -> InsightCard:
    """Compile an InsightCard for a SourceItem, RSS / metadata FIRST.

    Strategy:
        1. Build a snapshot text from the item's stored metadata.
        2. If the snapshot has enough content, compile from it directly
           (NO URL fetch — so a 403 on the original URL does not block it).
        3. Otherwise, fall back to the full-text pipeline compile_url().

    Never raises — always returns an InsightCard (completed or failed).
    """
    if snapshot_is_sufficient(item):
        snapshot_text = build_source_item_snapshot_text(item)
        title = item.title if (item.title and not _is_weak_title(item.title)) else None
        logger.info(
            f"Compiling SourceItem {item.id} from metadata snapshot "
            f"({len(snapshot_text)} chars) — skipping URL fetch"
        )
        return compile_text_snapshot(
            db,
            source_url=item.url,
            source_title=title,
            snapshot_text=snapshot_text,
            generation_basis="source_snapshot",
        )

    logger.info(
        f"SourceItem {item.id} snapshot insufficient — falling back to URL fetch"
    )
    return compile_url(db, item.url)


def compile_text_snapshot(
    db: Session,
    source_url: str,
    source_title: str | None,
    snapshot_text: str,
    generation_basis: str = "source_snapshot",
) -> InsightCard:
    """Compile an InsightCard directly from pre-supplied snapshot text.

    Does NOT fetch the URL and does NOT extract content. The snapshot text
    (RSS / source metadata) is cleaned, hashed, deduplicated, then handed to
    the LLM with an explicit "this is not the full text" instruction.

    Never raises — always returns an InsightCard.
    """
    logger.info(f"Starting snapshot compilation for: {source_url} (basis={generation_basis})")

    # Step 1: Clean the snapshot text (no fetch, no extract)
    try:
        cleaned_text = clean_text(snapshot_text or "")
    except Exception as e:
        logger.error(f"Failed to clean snapshot text: {e}")
        return _create_failed_card(db, source_url, SourceType.UNKNOWN, "", "", f"Snapshot cleaning failed: {e}")

    if not cleaned_text or len(cleaned_text) < SNAPSHOT_MIN_CHARS:
        msg = f"Snapshot text too short ({len(cleaned_text)} chars)"
        logger.error(msg)
        return _create_failed_card(db, source_url, SourceType.UNKNOWN, cleaned_text, "", msg)

    # Step 2: Hash + dedup
    try:
        content_hash = compute_content_hash(cleaned_text)
    except Exception as e:
        logger.error(f"Failed to compute snapshot hash: {e}")
        return _create_failed_card(db, source_url, SourceType.UNKNOWN, cleaned_text, "", f"Hash computation failed: {e}")

    try:
        existing = check_duplicate(db, source_url, content_hash)
        if existing:
            logger.info(f"Duplicate snapshot found: existing card {existing.id}")
            return existing
    except Exception as e:
        logger.error(f"Failed to check snapshot duplicate: {e}")
        # Non-fatal, continue

    # Step 3: LLM client
    try:
        client = create_llm_client()
    except ValueError as e:
        logger.error(f"LLM config error: {e}")
        return _create_failed_card(db, source_url, SourceType.UNKNOWN, cleaned_text, content_hash, str(e))
    except Exception as e:
        logger.error(f"Failed to create LLM client: {e}")
        return _create_failed_card(db, source_url, SourceType.UNKNOWN, cleaned_text, content_hash, f"LLM client init failed: {e}")

    # Step 4: Call LLM with explicit "not full text" basis
    try:
        llm_result = client.generate_json(
            system_prompt=INSIGHT_SYSTEM_PROMPT,
            user_prompt=build_insight_user_prompt(
                source_content=cleaned_text,
                user_directions=get_user_directions(),
                max_chars=MAX_LLM_INPUT_CHARS,
                source_basis=generation_basis,
            ),
        )
    except Exception as e:
        logger.error(f"LLM call failed for snapshot {source_url}: {e}")
        return _create_failed_card(db, source_url, SourceType.UNKNOWN, cleaned_text, content_hash, f"LLM call failed: {e}")

    # Step 5: Build card, annotating the snapshot basis so it is never
    # mistaken for a full-text insight.
    summary_zh = llm_result.get("summary_zh") or ""
    if SNAPSHOT_BASIS_NOTE not in summary_zh:
        summary_zh = f"{SNAPSHOT_BASIS_NOTE} {summary_zh}".strip()

    risks = list(llm_result.get("risks_zh") or [])
    if not any("全文未抓取" in str(r) for r in risks):
        risks.insert(0, SNAPSHOT_RISK_NOTE)

    preview_body = cleaned_text[:1000] if len(cleaned_text) > 1000 else cleaned_text
    cleaned_text_preview = f"{SNAPSHOT_BASIS_NOTE}\n{preview_body}"

    card = InsightCard(
        source_url=source_url,
        source_type=SourceType.UNKNOWN,
        source_title=llm_result.get("source_title") or source_title,
        source_author=llm_result.get("source_author"),
        source_published_at=llm_result.get("source_published_at"),
        content_hash=content_hash,
        cleaned_text_preview=cleaned_text_preview[:1000],
        status=CardStatus.COMPLETED,
        error_message=None,
        summary_zh=summary_zh,
        key_points_zh=json.dumps(llm_result.get("key_points_zh") or [], ensure_ascii=False),
        technical_insights_zh=json.dumps(llm_result.get("technical_insights_zh") or [], ensure_ascii=False),
        product_opportunities_zh=json.dumps(llm_result.get("product_opportunities_zh") or [], ensure_ascii=False),
        risks_zh=json.dumps(risks, ensure_ascii=False),
        action_items_zh=json.dumps(llm_result.get("action_items_zh") or [], ensure_ascii=False),
        relevance_score=llm_result.get("relevance_score") or 0,
        relevance_reasons_zh=json.dumps(llm_result.get("relevance_reasons_zh") or [], ensure_ascii=False),
        related_user_directions=json.dumps(llm_result.get("related_user_directions") or [], ensure_ascii=False),
        model_name=llm_result.get("model_name"),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    db.add(card)
    db.commit()
    db.refresh(card)

    logger.info(f"Created snapshot InsightCard {card.id} for {source_url}")
    return card


def _create_failed_card(
    db: Session,
    url: str,
    source_type: SourceType,
    cleaned_text: str,
    content_hash: str,
    error_message: str,
) -> InsightCard:
    """Create a failed InsightCard record."""
    card = InsightCard(
        source_url=url,
        source_type=source_type,
        content_hash=content_hash,
        cleaned_text_preview=cleaned_text[:1000] if len(cleaned_text) > 1000 else cleaned_text,
        status=CardStatus.FAILED,
        error_message=error_message,
        relevance_score=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return card
