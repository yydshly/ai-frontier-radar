"""SourceItem insight card generation from summary snapshots.

V1.0-beta.12: Rule-based assembly of InsightCard from existing summary_json.
Does NOT call any LLM. No network access. No schema changes.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import InsightCard, CardStatus, SourceItem


# Source weight bonuses for relevance scoring
_SOURCE_WEIGHT_BONUS: dict[str, int] = {
    "openai_news": 10,
    "anthropic_news": 10,
    "deepmind_blog": 8,
    "huggingface_blog": 7,
    "meta_ai_blog": 7,
    "nvidia_ai_blog": 7,
    "microsoft_ai_source": 6,
    "stanford_hai": 5,
    "mit_news_ai": 5,
    "arxiv_cs_ai": 4,
    "arxiv_cs_cl": 3,
    "arxiv_cs_lg": 3,
    "mistral_ai_news": 5,
    "cohere_blog": 5,
    "berkeley_bair_blog": 4,
}


def _parse_metadata(raw: Optional[str]) -> dict[str, Any]:
    """Parse raw_metadata_json string to dict."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _dump_metadata(raw: dict[str, Any]) -> str:
    """Serialize dict to JSON string."""
    return json.dumps(raw, ensure_ascii=False)


def _compute_relevance_score(
    source_key: Optional[str],
    related_directions: list[str],
    action_suggestions: list[str],
    risk_notes: list[str],
) -> int:
    """Compute relevance score using rule-based scoring."""
    score = 50
    score += min(len(related_directions), 5) * 8
    score += min(len(action_suggestions), 3) * 5
    score += _SOURCE_WEIGHT_BONUS.get(source_key or "", 0)
    score -= min(len(risk_notes), 3) * 2
    return max(0, min(100, score))


def _build_input_from_item(item: SourceItem, raw: dict[str, Any]) -> Optional[dict]:
    """Build a dict representation of InsightBuildInput from SourceItem."""
    summary_json = raw.get("summary_json", {})
    if not isinstance(summary_json, dict):
        summary_json = {}

    return {
        "source_item_id": item.id,
        "url": item.url,
        "title": item.title,
        "source_key": item.source_key,
        "zh_title": raw.get("zh_title"),
        "zh_summary": raw.get("zh_summary"),
        "fact_points": summary_json.get("fact_points", []),
        "source_claims": summary_json.get("source_claims", []),
        "model_inferences": summary_json.get("model_inferences", []),
        "related_directions": summary_json.get("related_directions", []),
        "personal_relevance": summary_json.get("personal_relevance"),
        "action_suggestions": summary_json.get("action_suggestions", []),
        "risk_notes": summary_json.get("risk_notes", []),
        "key_terms": summary_json.get("key_terms", []),
    }


def generate_source_item_insight(
    db: Session,
    item_id: int,
    *,
    force: bool = False,
) -> "InsightBuildResult":
    """
    Generate an InsightCard from a SourceItem's summary_json.

    Args:
        db: Database session
        item_id: SourceItem ID
        force: If True, regenerate even if already exists

    Returns:
        InsightBuildResult with status and data
    """
    # Step 1: Find item
    item = db.query(SourceItem).filter(SourceItem.id == item_id).first()
    if item is None:
        return InsightBuildResult(
            status=InsightStatus.NOT_ELIGIBLE,
            source_item_id=item_id,
            error=InsightError.ITEM_NOT_FOUND,
        )

    # Step 2: Parse raw_metadata_json
    raw = _parse_metadata(item.raw_metadata_json)

    # Step 3: Check eligibility
    summary_status = raw.get("summary_status")
    if summary_status != "generated":
        return InsightBuildResult(
            status=InsightStatus.NOT_ELIGIBLE,
            source_item_id=item_id,
            error=InsightError.SUMMARY_NOT_GENERATED,
            message="请先基于正文生成摘要",
        )

    summary_basis = raw.get("summary_basis")
    if summary_basis != "html_snapshot":
        return InsightBuildResult(
            status=InsightStatus.NOT_ELIGIBLE,
            source_item_id=item_id,
            error=InsightError.SUMMARY_BASIS_NOT_SNAPSHOT,
            message="摘要必须基于 HTML 正文快照生成",
        )

    zh_summary = raw.get("zh_summary")
    summary_json = raw.get("summary_json", {})
    if not isinstance(summary_json, dict):
        summary_json = {}

    if not zh_summary and not summary_json:
        return InsightBuildResult(
            status=InsightStatus.NOT_ELIGIBLE,
            source_item_id=item_id,
            error=InsightError.SUMMARY_MISSING,
            message="摘要内容为空",
        )

    # Step 4: Check existing insight card (skip if exists and not forced)
    if item.insight_card_id and not force:
        return InsightBuildResult(
            status=InsightStatus.SKIPPED,
            source_item_id=item_id,
            insight_card_id=item.insight_card_id,
            message="已有洞察卡",
        )

    # Step 5: Build input data
    input_data = _build_input_from_item(item, raw)
    if input_data is None:
        return InsightBuildResult(
            status=InsightStatus.FAILED,
            source_item_id=item_id,
            error=InsightError.CARD_CREATION_FAILED,
        )

    # Step 6: Extract and prepare fields
    source_url = item.url or ""
    source_title = input_data["zh_title"] or item.title or "无标题"
    summary = input_data["zh_summary"] or ""

    key_points = list(input_data["fact_points"]) + list(input_data["source_claims"])
    opportunities = list(input_data["action_suggestions"])
    if input_data["personal_relevance"]:
        opportunities.append(input_data["personal_relevance"])
    risks = list(input_data["risk_notes"])
    action_items = list(input_data["action_suggestions"])

    # Store extra metadata in existing JSON text fields
    # key_terms + related_directions go into related_user_directions
    extended_directions = (
        list(input_data["related_directions"])
        + [f"关键词:{k}" for k in input_data["key_terms"][:5]]
    )
    # model_inferences stored in technical_insights_zh
    extended_technical = list(input_data["model_inferences"][:5])
    extended_technical.append("生成依据:summary_from_snapshot")

    relevance_score = _compute_relevance_score(
        source_key=input_data["source_key"],
        related_directions=input_data["related_directions"],
        action_suggestions=input_data["action_suggestions"],
        risk_notes=input_data["risk_notes"],
    )

    # Step 7: Create or update InsightCard
    card_id = item.insight_card_id
    is_update = card_id is not None and force

    if is_update:
        card = db.query(InsightCard).filter(InsightCard.id == card_id).first()
        if card is None:
            # Card was deleted externally, create new one
            is_update = False

    if is_update and card:
        # Update existing card fields
        card.source_url = source_url
        card.source_title = source_title
        card.summary_zh = summary
        card.key_points_zh = json.dumps(key_points[:10], ensure_ascii=False)
        card.technical_insights_zh = json.dumps(extended_technical, ensure_ascii=False)
        card.product_opportunities_zh = json.dumps(opportunities[:5], ensure_ascii=False)
        card.risks_zh = json.dumps(risks[:5], ensure_ascii=False)
        card.action_items_zh = json.dumps(action_items[:5], ensure_ascii=False)
        card.relevance_score = relevance_score
        card.related_user_directions = json.dumps(extended_directions[:10], ensure_ascii=False)
        card.updated_at = datetime.utcnow()
        item.updated_at = datetime.utcnow()
        _write_insight_status(item, db, InsightStatus.GENERATED, insight_card_id=card.id)
        db.commit()
        db.refresh(card)
        return InsightBuildResult(
            status="updated",
            source_item_id=item_id,
            insight_card_id=card.id,
            message="洞察卡已更新",
        )
    else:
        # Create new card
        card = InsightCard(
            source_url=source_url,
            source_title=source_title,
            status=CardStatus.COMPLETED,
            summary_zh=summary,
            key_points_zh=json.dumps(key_points[:10], ensure_ascii=False),
            technical_insights_zh=json.dumps(extended_technical, ensure_ascii=False),
            product_opportunities_zh=json.dumps(opportunities[:5], ensure_ascii=False),
            risks_zh=json.dumps(risks[:5], ensure_ascii=False),
            action_items_zh=json.dumps(action_items[:5], ensure_ascii=False),
            relevance_score=relevance_score,
            related_user_directions=json.dumps(extended_directions[:10], ensure_ascii=False),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(card)
        db.flush()
        item.insight_card_id = card.id
        item.updated_at = datetime.utcnow()
        _write_insight_status(item, db, InsightStatus.GENERATED, insight_card_id=card.id)
        db.commit()
        db.refresh(card)
        return InsightBuildResult(
            status=InsightStatus.GENERATED,
            source_item_id=item_id,
            insight_card_id=card.id,
            message="洞察卡已生成",
        )


def _write_insight_status(
    item: SourceItem,
    db: Session,
    status: str,
    insight_card_id: Optional[int] = None,
    error: Optional[str] = None,
) -> None:
    """Write insight status to raw_metadata_json."""
    raw = _parse_metadata(item.raw_metadata_json)
    raw["insight_status"] = status
    raw["insight_updated_at"] = datetime.utcnow().isoformat()
    raw["insight_basis"] = "summary_from_snapshot"
    if insight_card_id is not None:
        raw["insight_card_id"] = insight_card_id
    if error:
        raw["insight_error"] = error
    else:
        raw.pop("insight_error", None)
    item.raw_metadata_json = _dump_metadata(raw)


def get_source_item_insight_status(item: SourceItem) -> tuple[str, str]:
    """Get the insight state and label for a SourceItem.

    Returns (state, label) tuple.
    """
    raw = _parse_metadata(item.raw_metadata_json)

    if item.insight_card_id:
        insight_status = raw.get("insight_status", "")
        if insight_status == "generated":
            return ("generated", "已生成")
        return ("has_card", "已有洞察卡")

    summary_status = raw.get("summary_status")
    summary_basis = raw.get("summary_basis")

    if summary_status == "generated" and summary_basis == "html_snapshot":
        return ("eligible", "可生成")

    if summary_status == "generated":
        return ("has_summary", "已有摘要")

    return ("missing", "未生成")
