"""Summary models and dataclasses."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class SummaryInput:
    """Input for summary generation."""
    source_item_id: int
    url: str
    title: str | None
    source_key: str | None
    source_name: str | None
    snapshot_text: str
    snapshot_title: str | None
    meta_description: str | None
    max_chars: int = 12000


@dataclass(frozen=True)
class SummaryResult:
    """Result of summary generation."""
    status: str  # generated | skipped | failed | disabled | missing_snapshot
    source_item_id: int
    zh_title: str | None = None
    zh_summary: str | None = None
    fact_points: list[str] = field(default_factory=list)
    source_claims: list[str] = field(default_factory=list)
    model_inferences: list[str] = field(default_factory=list)
    related_directions: list[str] = field(default_factory=list)
    personal_relevance: str | None = None
    action_suggestions: list[str] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)
    key_terms: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class LLMResponse:
    """Response from LLM client."""
    status: str  # ok | disabled | failed
    text: str | None = None
    error: str | None = None


@dataclass
class SummarySettings:
    """Summary generation settings from environment."""
    enabled: bool = False
    provider: str = "openai_compatible"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout_seconds: int = 30
    max_input_chars: int = 12000
    max_summary_chars: int = 500

    @classmethod
    def from_env(cls) -> "SummarySettings":
        return cls(
            enabled=_env_bool("LLM_SUMMARY_ENABLED", False),
            provider=os.getenv("LLM_PROVIDER", "openai_compatible").strip() or "openai_compatible",
            base_url=os.getenv("LLM_BASE_URL", "").strip(),
            api_key=os.getenv("LLM_API_KEY", "").strip(),
            model=os.getenv("LLM_MODEL", "").strip(),
            timeout_seconds=_env_int("LLM_TIMEOUT_SECONDS", 30, 5, 120),
            max_input_chars=_env_int("LLM_MAX_INPUT_CHARS", 12000, 1000, 50000),
            max_summary_chars=_env_int("LLM_MAX_SUMMARY_CHARS", 500, 100, 2000),
        )


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if value < minimum or value > maximum:
        return default
    return value


# Summary status values
class SummaryStatus:
    GENERATED = "generated"
    SKIPPED = "skipped"
    FAILED = "failed"
    DISABLED = "disabled"
    MISSING_SNAPSHOT = "missing_snapshot"
    NOT_ELIGIBLE = "not_eligible"


# Error codes
class SummaryError:
    DISABLED = "summary_disabled"
    MISSING_SNAPSHOT = "missing_snapshot"
    SNAPSHOT_EMPTY = "snapshot_empty"
    LLM_NOT_CONFIGURED = "llm_not_configured"
    LLM_TIMEOUT = "llm_timeout"
    LLM_ERROR = "llm_error"
    JSON_PARSE_FAILED = "json_parse_failed"
    SUMMARY_WRITE_FAILED = "summary_write_failed"
