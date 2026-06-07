"""InsightCard quality inspection — checks if a card meets minimum quality bar.

Does NOT call LLM, does NOT make network requests.
"""
import json
from typing import Any

from app.models import InsightCard, CardStatus


def inspect_insight_card_quality(card: InsightCard) -> dict:
    """Inspect an InsightCard and return quality metrics.

    Args:
        card: InsightCard ORM object.

    Returns:
        dict with keys:
            - summary_present: bool
            - key_points_count: int
            - technical_insights_count: int
            - product_opportunities_count: int
            - risks_count: int
            - action_items_count: int
            - relevance_score_present: bool
            - related_directions_count: int
            - passed_minimum_quality: bool
            - warnings: list[str]
    """
    warnings: list[str] = []

    # Check summary
    summary_present = bool(card.summary_zh and card.summary_zh.strip())

    # Helper to safely parse JSON fields
    def json_field_count(field_value: Any) -> int:
        if not field_value:
            return 0
        if isinstance(field_value, str):
            try:
                parsed = json.loads(field_value)
                if isinstance(parsed, list):
                    return len(parsed)
                return 0
            except (json.JSONDecodeError, TypeError):
                return 0
        if isinstance(field_value, list):
            return len(field_value)
        return 0

    key_points_count = json_field_count(card.key_points_zh)
    technical_insights_count = json_field_count(card.technical_insights_zh)
    product_opportunities_count = json_field_count(card.product_opportunities_zh)
    risks_count = json_field_count(card.risks_zh)
    action_items_count = json_field_count(card.action_items_zh)
    related_directions_count = json_field_count(card.related_user_directions)

    # Check relevance score
    relevance_score_present = card.relevance_score is not None and card.relevance_score > 0

    # Count non-empty structured fields
    structured_fields_with_content = 0
    if key_points_count > 0:
        structured_fields_with_content += 1
    if technical_insights_count > 0:
        structured_fields_with_content += 1
    if product_opportunities_count > 0:
        structured_fields_with_content += 1
    if action_items_count > 0:
        structured_fields_with_content += 1

    # Minimum quality bar:
    # - summary_zh non-empty
    # - at least 2 structured fields with content
    # - relevance_score present
    passed_minimum_quality = (
        summary_present
        and structured_fields_with_content >= 2
        and relevance_score_present
    )

    # Generate warnings
    if not summary_present:
        warnings.append("summary_zh is empty")
    if key_points_count == 0 and technical_insights_count == 0:
        warnings.append("No key_points or technical_insights")
    if product_opportunities_count == 0 and action_items_count == 0:
        warnings.append("No product_opportunities or action_items")
    if not relevance_score_present:
        warnings.append("relevance_score is missing or zero")
    if card.status == CardStatus.FAILED:
        warnings.append(f"Card status is FAILED: {card.error_message}")

    return {
        "summary_present": summary_present,
        "key_points_count": key_points_count,
        "technical_insights_count": technical_insights_count,
        "product_opportunities_count": product_opportunities_count,
        "risks_count": risks_count,
        "action_items_count": action_items_count,
        "relevance_score_present": relevance_score_present,
        "related_directions_count": related_directions_count,
        "passed_minimum_quality": passed_minimum_quality,
        "warnings": warnings,
    }
