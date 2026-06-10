"""Insight card generation from summary snapshots.

V1.0-beta.12: Generate InsightCard from SourceItem.raw_metadata_json.summary_json
without calling LLM. Uses rule-based assembly from existing summary data.
"""
from app.application.insight.insight_models import (
    InsightBuildInput,
    InsightBuildResult,
    InsightStatus,
    InsightError,
)
from app.application.insight.source_item_insight_service import (
    generate_source_item_insight,
    get_source_item_insight_status,
)

__all__ = [
    "InsightBuildInput",
    "InsightBuildResult",
    "InsightStatus",
    "InsightError",
    "generate_source_item_insight",
    "get_source_item_insight_status",
]
