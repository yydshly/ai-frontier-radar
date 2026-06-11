"""Centralized configuration for the radar application layer.

All numeric limits and feature gates are read from environment variables with
sensible defaults and safe fallbacks. This module does NOT write to the
database and does NOT call any LLM.

Usage:
    from app.application.radar.settings import (
        get_daily_scope_settings,
        get_recommendation_settings,
        get_generation_settings,
    )

    scope = get_daily_scope_settings()
    print(scope.window_hours)        # e.g. 24
    print(scope.item_limit)         # e.g. 50
    print(scope.briefing_limit)     # e.g. 50
"""
from __future__ import annotations

import os
from dataclasses import dataclass


# ── Helper functions ──────────────────────────────────────────────────────────────

def _env_bool(name: str, default: bool) -> bool:
    """Parse a boolean environment variable.

    Recognized true values (case-insensitive): "1", "true", "yes", "on"
    All other values (including unset) return ``default``.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    """Parse an integer environment variable with clamping.

    Invalid, negative, or out-of-range values fall back to ``default``.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        return default
    if value < minimum or value > maximum:
        return default
    return value


# ── Daily scope settings ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class DailyScopeSettings:
    """Run-time limits for the user-facing daily radar."""

    window_hours: int           # rolling time window (hours)
    item_limit: int            # max candidate items in the radar
    briefing_limit: int         # max items in the daily briefing
    today_focus_size: int      # top-N items shown as "最新发现"
    report_ready_threshold: int # min readable items before report_status="ready"


def get_daily_scope_settings() -> DailyScopeSettings:
    """Build DailyScopeSettings from environment variables."""
    return DailyScopeSettings(
        window_hours=_env_int("RADAR_DAILY_WINDOW_HOURS", default=24, minimum=1, maximum=168),
        item_limit=_env_int("RADAR_DAILY_ITEM_LIMIT", default=50, minimum=1, maximum=200),
        briefing_limit=_env_int("RADAR_DAILY_BRIEFING_LIMIT", default=50, minimum=1, maximum=200),
        today_focus_size=_env_int("RADAR_TODAY_FOCUS_SIZE", default=5, minimum=1, maximum=20),
        report_ready_threshold=_env_int(
            "RADAR_DAILY_REPORT_READY_THRESHOLD", default=5, minimum=1, maximum=50
        ),
    )


# ── Recommendation settings ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class RadarRecommendationSettings:
    """Limits for the compile-candidates / recommended insight pipeline."""

    limit: int                 # max candidates returned
    per_source_limit: int      # max candidates per single source
    max_scan: int              # max items to scan when building candidates
    insight_limit: int         # max batch-insight items per trigger (legacy, use insight_hard_cap)
    insight_hard_cap: int      # absolute safety ceiling for one batch trigger


def get_recommendation_settings() -> RadarRecommendationSettings:
    """Build RadarRecommendationSettings from environment variables."""
    return RadarRecommendationSettings(
        limit=_env_int("RADAR_RECOMMENDED_LIMIT", default=10, minimum=1, maximum=50),
        per_source_limit=_env_int(
            "RADAR_RECOMMENDED_PER_SOURCE_LIMIT", default=3, minimum=1, maximum=10
        ),
        max_scan=_env_int("RADAR_RECOMMENDED_MAX_SCAN", default=300, minimum=10, maximum=1000),
        insight_limit=_env_int(
            "RADAR_RECOMMENDED_INSIGHT_LIMIT", default=9999, minimum=1, maximum=9999
        ),
        insight_hard_cap=_env_int(
            "RADAR_RECOMMENDED_INSIGHT_HARD_CAP", default=20, minimum=1, maximum=100
        ),
    )


# ── Generation / processing settings ────────────────────────────────────────────

@dataclass(frozen=True)
class RadarGenerationSettings:
    """Limits for LLM-generation actions (summary batch, daily report)."""

    summary_batch_limit: int   # max items in one summary-generation batch


def get_generation_settings() -> RadarGenerationSettings:
    """Build RadarGenerationSettings from environment variables."""
    return RadarGenerationSettings(
        summary_batch_limit=_env_int(
            "RADAR_SUMMARY_BATCH_LIMIT", default=50, minimum=1, maximum=50
        ),
    )


# ── Daily report settings (already exist in daily_report.py, mirrored here) ─────

def get_daily_report_enabled() -> bool:
    """Return whether LLM daily report generation is enabled."""
    return _env_bool("DAILY_REPORT_ENABLED", default=False)


def get_daily_report_max_items() -> int:
    """Return the max items included in one daily report LLM call."""
    return _env_int("DAILY_REPORT_MAX_ITEMS", default=50, minimum=1, maximum=50)


def get_daily_broadcast_tts_enabled() -> bool:
    """Return whether TTS audio generation is enabled."""
    return _env_bool("DAILY_BROADCAST_TTS_ENABLED", default=False)
