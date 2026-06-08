"""InsightCard quality inspection — checks if a card meets minimum quality bar.

Does NOT call LLM, does NOT make network requests.
"""
import json
from typing import Any

from app.models import InsightCard, CardStatus, InsightCardBilingualReport


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


def inspect_bilingual_report_quality(report: InsightCardBilingualReport) -> dict:
    """Inspect a bilingual report and return quality metrics.

    Args:
        report: InsightCardBilingualReport ORM object.

    Returns:
        dict with keys:
            - english_summary_present: bool
            - english_key_claims_count: int
            - english_evidence_points_count: int
            - key_terms_count: int
            - chinese_explanation_present: bool
            - fidelity_notes_present: bool
            - interpretation_boundary_present: bool
            - passed_minimum_quality: bool
            - warnings: list[str]
    """
    warnings: list[str] = []

    # Check english_core_summary
    english_summary_present = bool(
        report.english_core_summary and report.english_core_summary.strip()
    )

    # Helper to safely parse JSON list fields
    def json_list_count(field_value: Any) -> int:
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

    english_key_claims_count = json_list_count(report.english_key_claims_json)
    english_evidence_points_count = json_list_count(report.english_evidence_points_json)
    key_terms_count = json_list_count(report.key_terms_json)

    # Check Chinese content
    chinese_explanation_present = bool(
        report.chinese_explanation and report.chinese_explanation.strip()
    )
    fidelity_notes_present = bool(
        report.fidelity_notes_zh and report.fidelity_notes_zh.strip()
    )
    interpretation_boundary_present = bool(
        report.interpretation_boundary_zh and report.interpretation_boundary_zh.strip()
    )

    # Minimum quality bar:
    # - english_core_summary non-empty
    # - english_key_claims >= 2
    # - chinese_explanation non-empty
    # - fidelity_notes_zh non-empty
    # - interpretation_boundary_zh non-empty
    passed_minimum_quality = (
        english_summary_present
        and english_key_claims_count >= 2
        and chinese_explanation_present
        and fidelity_notes_present
        and interpretation_boundary_present
    )

    # Generate warnings
    if not english_summary_present:
        warnings.append("english_core_summary is empty")
    if english_key_claims_count < 2:
        warnings.append(f"english_key_claims has only {english_key_claims_count} items (minimum 2)")
    if not chinese_explanation_present:
        warnings.append("chinese_explanation is empty")
    if not fidelity_notes_present:
        warnings.append("fidelity_notes_zh is empty")
    if not interpretation_boundary_present:
        warnings.append("interpretation_boundary_zh is empty")

    return {
        "english_summary_present": english_summary_present,
        "english_key_claims_count": english_key_claims_count,
        "english_evidence_points_count": english_evidence_points_count,
        "key_terms_count": key_terms_count,
        "chinese_explanation_present": chinese_explanation_present,
        "fidelity_notes_present": fidelity_notes_present,
        "interpretation_boundary_present": interpretation_boundary_present,
        "passed_minimum_quality": passed_minimum_quality,
        "warnings": warnings,
    }
