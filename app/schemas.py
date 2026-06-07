"""Pydantic schemas for request/response validation."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, HttpUrl


class CompileRequest(BaseModel):
    url: str


class CardListItem(BaseModel):
    id: int
    source_title: Optional[str]
    source_url: str
    status: str
    relevance_score: int
    created_at: datetime

    class Config:
        from_attributes = True


class CardDetail(BaseModel):
    id: int
    source_url: str
    source_type: str
    source_title: Optional[str]
    source_author: Optional[str]
    source_published_at: Optional[str]
    status: str
    error_message: Optional[str]

    summary_zh: Optional[str]
    key_points_zh: Optional[str]
    technical_insights_zh: Optional[str]
    product_opportunities_zh: Optional[str]
    risks_zh: Optional[str]
    action_items_zh: Optional[str]

    relevance_score: int
    relevance_reasons_zh: Optional[str]
    related_user_directions: Optional[str]

    model_name: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    status: str
