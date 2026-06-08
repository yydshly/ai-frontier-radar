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


def _looks_english(text: str | None) -> bool:
    """Check if text looks primarily English (not Chinese).

    Simple heuristic: counts Latin alphabetic characters vs Chinese characters.
    Returns True if the text has substantially more Latin chars than Chinese chars.
    """
    if not text:
        return False
    stripped = text.strip()
    if not stripped:
        return False
    latin_count = sum(1 for c in stripped if c.isalpha() and ("A" <= c <= "Z" or "a" <= c <= "z"))
    chinese_count = sum(1 for c in stripped if "一" <= c <= "鿿")
    # Looks English if: mostly Latin chars, and Latin chars significantly outnumber Chinese
    return latin_count > 0 and (chinese_count == 0 or latin_count > chinese_count * 3)


def _looks_chinese(text: str | None) -> bool:
    """Check if text looks primarily Chinese.

    Simple heuristic: returns True if text contains a meaningful amount of Chinese characters.
    """
    if not text:
        return False
    stripped = text.strip()
    if not stripped:
        return False
    chinese_count = sum(1 for c in stripped if "一" <= c <= "鿿")
    # Looks Chinese if: at least 4 Chinese characters and they form a reasonable proportion
    return chinese_count >= 4


def inspect_bilingual_report_quality(report: InsightCardBilingualReport) -> dict:
    """Inspect a bilingual report and return quality metrics.

    V0.8.2: adds language checks to verify English fields look English
    and Chinese fields look Chinese.

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
            - english_summary_looks_english: bool
            - english_key_claims_look_english: bool
            - chinese_explanation_looks_chinese: bool
            - fidelity_notes_look_chinese: bool
            - interpretation_boundary_look_chinese: bool
            - passed_minimum_quality: bool
            - warnings: list[str]
    """
    warnings: list[str] = []

    # Check english_core_summary
    english_summary_present = bool(
        report.english_core_summary and report.english_core_summary.strip()
    )
    english_summary_looks_english = _looks_english(report.english_core_summary)

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

    # Check English key claims language (sample first item if any)
    english_key_claims_look_english = False
    try:
        claims_list = json.loads(report.english_key_claims_json) if report.english_key_claims_json else []
        if claims_list:
            sample = claims_list[0] if isinstance(claims_list[0], str) else str(claims_list[0])
            english_key_claims_look_english = _looks_english(sample)
        else:
            english_key_claims_look_english = True  # empty list, no language to check
    except (json.JSONDecodeError, TypeError, IndexError):
        english_key_claims_look_english = False

    # Check Chinese content
    chinese_explanation_present = bool(
        report.chinese_explanation and report.chinese_explanation.strip()
    )
    chinese_explanation_looks_chinese = _looks_chinese(report.chinese_explanation)
    fidelity_notes_present = bool(
        report.fidelity_notes_zh and report.fidelity_notes_zh.strip()
    )
    fidelity_notes_look_chinese = _looks_chinese(report.fidelity_notes_zh)
    interpretation_boundary_present = bool(
        report.interpretation_boundary_zh and report.interpretation_boundary_zh.strip()
    )
    interpretation_boundary_look_chinese = _looks_chinese(report.interpretation_boundary_zh)

    # Minimum quality bar (V0.8.2):
    # - english_core_summary non-empty AND looks like English
    # - english_key_claims >= 2 AND looks like English
    # - chinese_explanation non-empty AND looks like Chinese
    # - fidelity_notes_zh non-empty AND looks like Chinese
    # - interpretation_boundary_zh non-empty AND looks like Chinese
    passed_minimum_quality = (
        english_summary_present
        and english_summary_looks_english
        and english_key_claims_count >= 2
        and english_key_claims_look_english
        and chinese_explanation_present
        and chinese_explanation_looks_chinese
        and fidelity_notes_present
        and fidelity_notes_look_chinese
        and interpretation_boundary_present
        and interpretation_boundary_look_chinese
    )

    # Generate warnings
    if not english_summary_present:
        warnings.append("english_core_summary is empty")
    elif not english_summary_looks_english:
        warnings.append("english_core_summary does not look like English")
    if english_key_claims_count < 2:
        warnings.append(f"english_key_claims has only {english_key_claims_count} items (minimum 2)")
    elif not english_key_claims_look_english:
        warnings.append("english_key_claims does not look like English")
    if not chinese_explanation_present:
        warnings.append("chinese_explanation is empty")
    elif not chinese_explanation_looks_chinese:
        warnings.append("chinese_explanation does not look like Chinese")
    if not fidelity_notes_present:
        warnings.append("fidelity_notes_zh is empty")
    elif not fidelity_notes_look_chinese:
        warnings.append("fidelity_notes_zh does not look like Chinese")
    if not interpretation_boundary_present:
        warnings.append("interpretation_boundary_zh is empty")
    elif not interpretation_boundary_look_chinese:
        warnings.append("interpretation_boundary_zh does not look like Chinese")

    return {
        "english_summary_present": english_summary_present,
        "english_key_claims_count": english_key_claims_count,
        "english_evidence_points_count": english_evidence_points_count,
        "key_terms_count": key_terms_count,
        "chinese_explanation_present": chinese_explanation_present,
        "fidelity_notes_present": fidelity_notes_present,
        "interpretation_boundary_present": interpretation_boundary_present,
        "english_summary_looks_english": english_summary_looks_english,
        "english_key_claims_look_english": english_key_claims_look_english,
        "chinese_explanation_looks_chinese": chinese_explanation_looks_chinese,
        "fidelity_notes_look_chinese": fidelity_notes_look_chinese,
        "interpretation_boundary_look_chinese": interpretation_boundary_look_chinese,
        "passed_minimum_quality": passed_minimum_quality,
        "warnings": warnings,
    }
