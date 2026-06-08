"""Data models for URL intake classification."""

from dataclasses import dataclass
from enum import Enum


class PageType(str, Enum):
    ARTICLE = "article"
    PDF = "pdf"
    FEED = "feed"
    LISTING = "listing"
    PAGINATION = "pagination"
    TAG_OR_CATEGORY = "tag_or_category"
    HOMEPAGE = "homepage"
    UNKNOWN = "unknown"


class RecommendedStrategy(str, Enum):
    COMPILE = "compile"
    DISCOVERY_ONLY = "discovery_only"
    MANUAL_REVIEW = "manual_review"
    REJECT = "reject"


@dataclass
class IntakeDecision:
    url: str
    page_type: PageType
    strategy: RecommendedStrategy
    can_compile_directly: bool
    confidence: float
    reason: str
