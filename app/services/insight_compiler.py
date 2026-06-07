"""InsightCard compilation orchestrator."""
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import InsightCard, CardStatus, SourceType
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


class CompilationError(Exception):
    """Raised when compilation fails at any step."""
    pass


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
