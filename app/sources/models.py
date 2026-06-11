"""Source Registry configuration data structures.

These are plain Python dataclasses — NOT SQLAlchemy database models.
Database models belong to app/models.py and are out of scope for V0.2.1.
"""
from dataclasses import dataclass
from typing import Literal

SourceType = Literal["rss", "html_index", "manual_pdf", "report_page"]
SourceCategory = Literal[
    "company", "research", "paper", "policy", "blog", "benchmark", "funding", "open_source"
]
FetchStrategy = Literal["rss", "html_index", "manual"]


@dataclass(frozen=True)
class SourceConfig:
    """Immutable configuration for a single information source."""

    source_key: str
    name: str
    description: str
    type: SourceType
    homepage_url: str | None
    feed_url: str | None
    category: SourceCategory
    tags: list[str]
    enabled: bool
    fetch_strategy: FetchStrategy
    relevance_hint: str
    fetch_interval_hours: int
    # Reliability annotations (optional; free-text in YAML). For display / review
    # only — they do NOT affect fetch decisions.
    strategy_notes: str = ""
    strategy_status: str = ""

    @property
    def is_rss(self) -> bool:
        return self.fetch_strategy == "rss"

    @property
    def is_html_index(self) -> bool:
        return self.fetch_strategy == "html_index"
