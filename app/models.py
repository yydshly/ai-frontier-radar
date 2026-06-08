"""SQLAlchemy models."""
import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, Enum, DateTime,
    Boolean, ForeignKey, UniqueConstraint,
)

from app.db import Base


class SourceType(str, enum.Enum):
    HTML = "html"
    PDF = "pdf"
    UNKNOWN = "unknown"


class CardStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class InsightCard(Base):
    __tablename__ = "insight_cards"

    id = Column(Integer, primary_key=True, index=True)

    # Source info
    source_url = Column(Text, nullable=False, index=True)
    source_type = Column(Enum(SourceType), default=SourceType.UNKNOWN)
    source_title = Column(Text)
    source_author = Column(Text)
    source_published_at = Column(Text)
    content_hash = Column(String(64), index=True)
    raw_text_path = Column(Text, nullable=True)

    # Content preview
    cleaned_text_preview = Column(Text)

    # Processing status
    status = Column(Enum(CardStatus), default=CardStatus.PENDING)
    error_message = Column(Text, nullable=True)

    # LLM-generated content
    summary_zh = Column(Text)
    key_points_zh = Column(Text)  # JSON list
    technical_insights_zh = Column(Text)  # JSON list
    product_opportunities_zh = Column(Text)  # JSON list
    risks_zh = Column(Text)  # JSON list
    action_items_zh = Column(Text)  # JSON list

    # Relevance
    relevance_score = Column(Integer, default=0)
    relevance_reasons_zh = Column(Text)  # JSON list
    related_user_directions = Column(Text)  # JSON list

    # Metadata
    model_name = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<InsightCard(id={self.id}, title={self.source_title}, status={self.status})>"


class Source(Base):
    """An information source to monitor for AI frontier content."""

    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    source_key = Column(String(128), nullable=False, unique=True, index=True)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=False)

    # Source classification
    source_type = Column(String(64), nullable=False)  # rss / html_index / manual_pdf / report_page
    homepage_url = Column(Text, nullable=True)
    feed_url = Column(Text, nullable=True)
    category = Column(String(64), nullable=False)  # company / research / paper / policy / blog / benchmark / funding / open_source
    tags_json = Column(Text, nullable=False, default="[]")

    # Fetch configuration
    enabled = Column(Boolean, nullable=False, default=True)
    fetch_strategy = Column(String(64), nullable=False)  # rss / html_index / manual
    relevance_hint = Column(Text, nullable=False, default="")
    fetch_interval_hours = Column(Integer, nullable=False, default=24)

    # Last fetch state
    last_checked_at = Column(DateTime, nullable=True)
    last_success_at = Column(DateTime, nullable=True)
    last_error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Source(id={self.id}, source_key={self.source_key}, name={self.name})>"


class SourceItem(Base):
    """A single article or document discovered from a Source."""

    __tablename__ = "source_items"
    __table_args__ = (
        UniqueConstraint("source_id", "url", name="uq_source_items_source_id_url"),
    )

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False, index=True)
    source_key = Column(String(128), nullable=False, index=True)

    # Content metadata
    url = Column(Text, nullable=False)
    canonical_url = Column(Text, nullable=True)
    title = Column(Text, nullable=True)
    author = Column(Text, nullable=True)
    published_at = Column(Text, nullable=True)

    # Deduplication
    content_hash = Column(String(64), nullable=True, index=True)
    raw_metadata_json = Column(Text, nullable=True)

    # Processing state
    status = Column(String(32), nullable=False, default="discovered")
    error_message = Column(Text, nullable=True)

    # InsightCard linkage
    insight_card_id = Column(Integer, ForeignKey("insight_cards.id"), nullable=True, index=True)

    # Timestamps
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<SourceItem(id={self.id}, source_key={self.source_key}, title={self.title}, status={self.status})>"


class FetchRun(Base):
    """A single fetch execution for a Source."""

    __tablename__ = "fetch_runs"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False, index=True)
    source_key = Column(String(128), nullable=False, index=True)

    run_type = Column(String(64), nullable=False, default="manual")  # manual / scheduled
    status = Column(String(32), nullable=False, default="pending")  # pending / running / success / partial_failed / failed

    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    items_found = Column(Integer, nullable=False, default=0)
    items_new = Column(Integer, nullable=False, default=0)
    items_updated = Column(Integer, nullable=False, default=0)
    items_failed = Column(Integer, nullable=False, default=0)

    error_message = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<FetchRun(id={self.id}, source_key={self.source_key}, status={self.status})>"


class CardDecision(Base):
    """User's own judgment on an InsightCard after reading it.

    V0.4: lets the user mark a card as worth_attention / related_to_me /
    read_later / ignore / to_action, with an optional note.

    One current decision per card (card_id is unique). Re-submitting updates
    the existing row instead of inserting a new one.
    """

    __tablename__ = "card_decisions"
    __table_args__ = (
        UniqueConstraint("card_id", name="uq_card_decisions_card_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    card_id = Column(Integer, ForeignKey("insight_cards.id"), nullable=False, index=True)
    decision = Column(String(64), nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<CardDecision(id={self.id}, card_id={self.card_id}, decision={self.decision})>"


class InsightCardBilingualReport(Base):
    """Bilingual (English-Chinese) report for an InsightCard.

    V0.8: adds an English core content layer with Chinese explanation
    to help users who are not comfortable reading English understand
    the original material while preserving fidelity to the source.

    One report per card (card_id is unique). Re-generating updates
    the existing row instead of inserting a new one.
    """

    __tablename__ = "insight_card_bilingual_reports"
    __table_args__ = (
        UniqueConstraint("card_id", name="uq_bilingual_reports_card_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    card_id = Column(Integer, ForeignKey("insight_cards.id"), nullable=False, index=True)

    # English core content (written in English)
    english_core_summary = Column(Text, nullable=True)
    english_key_claims_json = Column(Text, nullable=True)
    english_evidence_points_json = Column(Text, nullable=True)
    key_terms_json = Column(Text, nullable=True)

    # Chinese explanation and fidelity notes (written in Chinese)
    chinese_explanation = Column(Text, nullable=True)
    fidelity_notes_zh = Column(Text, nullable=True)
    interpretation_boundary_zh = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<InsightCardBilingualReport(id={self.id}, card_id={self.card_id})>"
