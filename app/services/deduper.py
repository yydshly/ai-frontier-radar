"""Content deduplication using hash."""
import hashlib

from sqlalchemy.orm import Session

from app.models import InsightCard, CardStatus


def compute_content_hash(text: str) -> str:
    """Compute SHA256 hash of cleaned text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_duplicate(db: Session, source_url: str, content_hash: str) -> InsightCard | None:
    """
    Check if a card with the same URL and content hash already exists.

    Returns:
        Existing InsightCard if duplicate found, None otherwise
    """
    return (
        db.query(InsightCard)
        .filter(
            InsightCard.source_url == source_url,
            InsightCard.content_hash == content_hash,
        )
        .first()
    )


def find_existing_by_url(db: Session, source_url: str) -> list[InsightCard]:
    """Find all cards with the same source URL."""
    return (
        db.query(InsightCard)
        .filter(InsightCard.source_url == source_url)
        .order_by(InsightCard.created_at.desc())
        .all()
    )
