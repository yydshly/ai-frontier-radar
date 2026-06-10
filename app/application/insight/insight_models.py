"""Insight build models and dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class InsightBuildInput:
    """Input for insight card generation from summary data."""
    source_item_id: int
    url: Optional[str]
    title: Optional[str]
    source_key: Optional[str]
    zh_title: Optional[str]
    zh_summary: Optional[str]
    fact_points: list[str] = field(default_factory=list)
    source_claims: list[str] = field(default_factory=list)
    model_inferences: list[str] = field(default_factory=list)
    related_directions: list[str] = field(default_factory=list)
    personal_relevance: Optional[str] = None
    action_suggestions: list[str] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)
    key_terms: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class InsightBuildResult:
    """Result of insight card generation."""
    status: str  # created | updated | skipped | failed | not_eligible
    source_item_id: int
    insight_card_id: Optional[int] = None
    message: Optional[str] = None
    error: Optional[str] = None


# Insight status values
class InsightStatus:
    GENERATED = "generated"
    SKIPPED = "skipped"
    FAILED = "failed"
    NOT_ELIGIBLE = "not_eligible"


# Error codes
class InsightError:
    ITEM_NOT_FOUND = "item_not_found"
    SUMMARY_MISSING = "summary_missing"
    SUMMARY_NOT_GENERATED = "summary_not_generated"
    SUMMARY_BASIS_NOT_SNAPSHOT = "summary_basis_not_snapshot"
    SUMMARY_JSON_INVALID = "summary_json_invalid"
    CARD_CREATION_FAILED = "card_creation_failed"
