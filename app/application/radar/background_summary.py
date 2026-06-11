"""Background Chinese-summary generation for today-radar items."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.application.candidates.one_liner import (
    CandidateOneLinerService,
    ELIGIBLE_STATUSES,
    get_one_liner_settings,
)
from app.db import SessionLocal
from app.models import SourceItem


SUMMARY_BATCH_STATUS_KEY = "radar_summary_batch_status"
SUMMARY_BATCH_ERROR_KEY = "radar_summary_batch_error"
SUMMARY_BATCH_UPDATED_AT_KEY = "radar_summary_batch_updated_at"


@dataclass(frozen=True)
class SummaryBatchEnqueueResult:
    accepted_ids: list[int] = field(default_factory=list)
    tracked_ids: list[int] = field(default_factory=list)
    skipped: int = 0
    failed: int = 0


def _metadata(item: SourceItem) -> dict[str, Any]:
    try:
        value = json.loads(item.raw_metadata_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _has_complete_summary(raw: dict[str, Any]) -> bool:
    return bool(
        str(raw.get("zh_one_liner") or "").strip()
        and str(raw.get("zh_summary") or "").strip()
    )


def _write_batch_state(
    item: SourceItem,
    raw: dict[str, Any],
    status: str,
    error: str | None = None,
) -> None:
    raw[SUMMARY_BATCH_STATUS_KEY] = status
    raw[SUMMARY_BATCH_UPDATED_AT_KEY] = datetime.utcnow().isoformat()
    if error:
        raw[SUMMARY_BATCH_ERROR_KEY] = error[:500]
    else:
        raw.pop(SUMMARY_BATCH_ERROR_KEY, None)
    item.raw_metadata_json = json.dumps(raw, ensure_ascii=False)
    item.updated_at = datetime.utcnow()


def enqueue_summary_batch(item_ids: list[int], *, hard_cap: int = 50) -> SummaryBatchEnqueueResult:
    """Mark eligible items as queued and return the accepted IDs."""
    ordered_ids = list(dict.fromkeys(item_ids))[:hard_cap]
    if not ordered_ids:
        return SummaryBatchEnqueueResult()

    db = SessionLocal()
    try:
        rows = db.query(SourceItem).filter(SourceItem.id.in_(ordered_ids)).all()
        rows_by_id = {row.id: row for row in rows}
        accepted_ids: list[int] = []
        tracked_ids: list[int] = []
        skipped = failed = 0

        for item_id in ordered_ids:
            item = rows_by_id.get(item_id)
            if item is None:
                failed += 1
                continue

            raw = _metadata(item)
            if _has_complete_summary(raw):
                skipped += 1
                continue

            current = str(raw.get(SUMMARY_BATCH_STATUS_KEY) or "")
            if current in {"queued", "running"}:
                tracked_ids.append(item_id)
                skipped += 1
                continue

            if item.status not in ELIGIBLE_STATUSES or not item.url:
                _write_batch_state(item, raw, "failed", "文章状态或链接不支持摘要生成")
                tracked_ids.append(item_id)
                failed += 1
                continue

            _write_batch_state(item, raw, "queued")
            accepted_ids.append(item_id)
            tracked_ids.append(item_id)

        db.commit()
        return SummaryBatchEnqueueResult(
            accepted_ids=accepted_ids,
            tracked_ids=tracked_ids,
            skipped=skipped,
            failed=failed,
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run_summary_batch_in_background(item_ids: list[int]) -> None:
    """Generate summaries sequentially in an isolated background DB session."""
    if not item_ids:
        return

    db = SessionLocal()
    try:
        service = CandidateOneLinerService(db, settings=get_one_liner_settings())
        for item_id in item_ids:
            item = db.query(SourceItem).filter(SourceItem.id == item_id).first()
            if item is None:
                continue

            raw = _metadata(item)
            if _has_complete_summary(raw):
                _write_batch_state(item, raw, "completed")
                db.commit()
                continue

            _write_batch_state(item, raw, "running")
            db.commit()

            try:
                result = service.generate_for_item(
                    item,
                    fill_missing_summary=True,
                    force=False,
                )
                db.refresh(item)
                raw = _metadata(item)
                if _has_complete_summary(raw):
                    _write_batch_state(item, raw, "completed")
                else:
                    _write_batch_state(
                        item,
                        raw,
                        "failed",
                        result.error or "模型未返回完整中文摘要",
                    )
                db.commit()
            except Exception as exc:
                db.rollback()
                item = db.query(SourceItem).filter(SourceItem.id == item_id).first()
                if item is not None:
                    _write_batch_state(item, _metadata(item), "failed", str(exc))
                    db.commit()
    finally:
        db.close()
