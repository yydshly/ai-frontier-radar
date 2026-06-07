"""SQLAlchemy models."""
import enum
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, Enum, DateTime

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
