"""SourceItem summary generation service.

Orchestrates loading snapshot, calling LLM, parsing JSON, and saving results.
Does NOT call LLM unless explicitly enabled and configured.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import SourceItem
from app.application.content.content_snapshot import load_snapshot, snapshot_exists
from app.application.summary.summary_models import (
    SummaryInput,
    SummaryResult,
    SummarySettings,
    SummaryStatus,
    SummaryError,
)
from app.application.summary.summary_prompt import build_summary_prompt
from app.application.summary.summary_llm_client import SummaryLLMClient, parse_summary_json


# Keys to read from snapshot
SNAPSHOT_TEXT_KEYS = ("text", "content", "body")
SNAPSHOT_TITLE_KEYS = ("title", "meta_description")


def get_summary_settings() -> SummarySettings:
    """Get summary settings from environment."""
    return SummarySettings.from_env()


def _load_snapshot_text(item_id: int) -> dict[str, Any] | None:
    """Load snapshot data for a source item."""
    if not snapshot_exists(item_id):
        return None
    return load_snapshot(item_id)


def _extract_snapshot_text(snapshot: dict[str, Any]) -> str | None:
    """Extract text content from snapshot dict."""
    for key in SNAPSHOT_TEXT_KEYS:
        text = snapshot.get(key)
        if isinstance(text, str) and len(text.strip()) > 0:
            return text.strip()
    return None


def _extract_snapshot_title(snapshot: dict[str, Any]) -> str | None:
    """Extract title from snapshot dict."""
    for key in SNAPSHOT_TITLE_KEYS:
        title = snapshot.get(key)
        if isinstance(title, str) and len(title.strip()) > 0:
            return title.strip()
    return None


def _parse_metadata(raw_metadata_json: str | None) -> dict[str, Any]:
    """Parse raw_metadata_json string to dict."""
    if not raw_metadata_json:
        return {}
    try:
        data = json.loads(raw_metadata_json)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _dump_metadata(raw: dict[str, Any]) -> str:
    """Serialize dict to JSON string."""
    return json.dumps(raw, ensure_ascii=False)


def generate_source_item_summary(
    db: Session,
    item_id: int,
    *,
    force: bool = False,
) -> SummaryResult:
    """
    Generate summary for a SourceItem from its content snapshot.

    Args:
        db: Database session
        item_id: SourceItem ID
        force: If True, regenerate even if already generated

    Returns:
        SummaryResult with status and data
    """
    # Step 1: Find item
    item = db.query(SourceItem).filter(SourceItem.id == item_id).first()
    if item is None:
        return SummaryResult(
            status=SummaryStatus.FAILED,
            source_item_id=item_id,
            error="item_not_found",
        )

    # Step 2: Check eligibility
    if not item.url:
        return SummaryResult(
            status=SummaryStatus.NOT_ELIGIBLE,
            source_item_id=item_id,
            error="no_url",
        )

    # Step 3: Check existing summary (skip if already generated and not forced)
    raw = _parse_metadata(item.raw_metadata_json)
    existing_status = raw.get("summary_status")
    if existing_status == SummaryStatus.GENERATED and not force:
        return SummaryResult(
            status=SummaryStatus.SKIPPED,
            source_item_id=item_id,
            zh_title=raw.get("zh_title"),
            zh_summary=raw.get("zh_summary"),
            error="already_generated",
        )

    # Step 4: Load snapshot
    snapshot = _load_snapshot_text(item_id)
    if snapshot is None:
        _write_summary_status(item, db, SummaryStatus.MISSING_SNAPSHOT, error=SummaryError.MISSING_SNAPSHOT)
        return SummaryResult(
            status=SummaryStatus.MISSING_SNAPSHOT,
            source_item_id=item_id,
            error=SummaryError.MISSING_SNAPSHOT,
        )

    # Step 5: Extract text
    snapshot_text = _extract_snapshot_text(snapshot)
    if not snapshot_text:
        _write_summary_status(item, db, SummaryStatus.FAILED, error=SummaryError.SNAPSHOT_EMPTY)
        return SummaryResult(
            status=SummaryStatus.FAILED,
            source_item_id=item_id,
            error=SummaryError.SNAPSHOT_EMPTY,
        )

    # Step 6: Extract title
    snapshot_title = _extract_snapshot_title(snapshot)

    # Step 7: Get settings and check if LLM is enabled
    settings = get_summary_settings()
    if not settings.enabled:
        _write_summary_status(item, db, SummaryStatus.DISABLED, error=SummaryError.DISABLED)
        return SummaryResult(
            status=SummaryStatus.DISABLED,
            source_item_id=item_id,
            error=SummaryError.DISABLED,
        )

    # Step 8: Build input
    # Truncate text to max chars
    truncated_text = snapshot_text[: settings.max_input_chars]
    summary_input = SummaryInput(
        source_item_id=item_id,
        url=item.url or "",
        title=item.title,
        source_key=item.source_key,
        source_name=None,  # Will be looked up if needed
        snapshot_text=truncated_text,
        snapshot_title=snapshot_title,
        meta_description=snapshot.get("meta_description"),
        max_chars=settings.max_input_chars,
    )

    # Step 9: Call LLM
    llm_client = SummaryLLMClient(settings)
    system_prompt, user_prompt = build_summary_prompt(
        content=summary_input.snapshot_text,
        url=summary_input.url,
        title=summary_input.title,
        source_name=summary_input.source_name,
        snapshot_title=summary_input.snapshot_title,
    )

    llm_response = llm_client.generate_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )

    if llm_response.status == "disabled":
        _write_summary_status(item, db, SummaryStatus.DISABLED, error=SummaryError.LLM_NOT_CONFIGURED)
        return SummaryResult(
            status=SummaryStatus.DISABLED,
            source_item_id=item_id,
            error=llm_response.error or SummaryError.LLM_NOT_CONFIGURED,
        )

    if llm_response.status == "failed":
        _write_summary_status(item, db, SummaryStatus.FAILED, error=llm_response.error)
        return SummaryResult(
            status=SummaryStatus.FAILED,
            source_item_id=item_id,
            error=llm_response.error,
        )

    # Step 10: Parse JSON
    raw_text = llm_response.text or ""
    try:
        data = parse_summary_json(raw_text)
    except ValueError as e:
        _write_summary_status(item, db, SummaryStatus.FAILED, error=SummaryError.JSON_PARSE_FAILED)
        return SummaryResult(
            status=SummaryStatus.FAILED,
            source_item_id=item_id,
            error=f"{SummaryError.JSON_PARSE_FAILED}: {e}",
        )

    # Step 11: Validate and extract fields
    zh_title = _safe_string(data.get("zh_title"))
    zh_summary = _safe_string(data.get("zh_summary"))
    fact_points = _safe_string_list(data.get("fact_points", []))
    source_claims = _safe_string_list(data.get("source_claims", []))
    model_inferences = _safe_string_list(data.get("model_inferences", []))
    related_directions = _safe_string_list(data.get("related_directions", []))
    personal_relevance = _safe_string(data.get("personal_relevance"))
    action_suggestions = _safe_string_list(data.get("action_suggestions", []))
    risk_notes = _safe_string_list(data.get("risk_notes", []))
    key_terms = _safe_string_list(data.get("key_terms", []))

    # Step 12: Write results
    summary_json = {
        "fact_points": fact_points,
        "source_claims": source_claims,
        "model_inferences": model_inferences,
        "related_directions": related_directions,
        "personal_relevance": personal_relevance,
        "action_suggestions": action_suggestions,
        "risk_notes": risk_notes,
        "key_terms": key_terms,
    }

    _write_summary_result(
        item,
        db,
        status=SummaryStatus.GENERATED,
        zh_title=zh_title,
        zh_summary=zh_summary,
        summary_json=summary_json,
        error=None,
    )

    return SummaryResult(
        status=SummaryStatus.GENERATED,
        source_item_id=item_id,
        zh_title=zh_title,
        zh_summary=zh_summary,
        fact_points=fact_points,
        source_claims=source_claims,
        model_inferences=model_inferences,
        related_directions=related_directions,
        personal_relevance=personal_relevance,
        action_suggestions=action_suggestions,
        risk_notes=risk_notes,
        key_terms=key_terms,
        error=None,
    )


def _safe_string(value: Any, max_length: int | None = None) -> str | None:
    """Convert value to string safely."""
    if value is None:
        return None
    if isinstance(value, str):
        result = value.strip()
        if max_length and len(result) > max_length:
            result = result[:max_length]
        return result if result else None
    return None


def _safe_string_list(value: Any) -> list[str]:
    """Convert value to list of strings."""
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, str):
            s = item.strip()
            if s:
                result.append(s)
    return result


def _write_summary_status(
    item: SourceItem,
    db: Session,
    status: str,
    error: str | None = None,
) -> None:
    """Write only status to raw_metadata_json."""
    raw = _parse_metadata(item.raw_metadata_json)
    raw["summary_status"] = status
    raw["summary_updated_at"] = datetime.utcnow().isoformat()
    if error:
        raw["summary_error"] = error
    item.raw_metadata_json = _dump_metadata(raw)
    db.commit()


def _write_summary_result(
    item: SourceItem,
    db: Session,
    status: str,
    zh_title: str | None,
    zh_summary: str | None,
    summary_json: dict[str, Any],
    error: str | None,
) -> None:
    """Write full summary result to raw_metadata_json."""
    raw = _parse_metadata(item.raw_metadata_json)
    raw["summary_status"] = status
    raw["summary_basis"] = "html_snapshot"
    raw["summary_updated_at"] = datetime.utcnow().isoformat()
    raw["zh_title"] = zh_title
    raw["zh_summary"] = zh_summary
    raw["summary_json"] = summary_json
    if error:
        raw["summary_error"] = error
    else:
        raw.pop("summary_error", None)

    item.raw_metadata_json = _dump_metadata(raw)
    item.updated_at = datetime.utcnow()
    db.add(item)
    db.commit()
    db.refresh(item)
