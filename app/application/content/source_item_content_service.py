"""SourceItem HTML content fetch service.

Orchestrates URL safety check, HTML fetch, snapshot save, and status update.
Does NOT call LLM.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import SourceItem
from app.application.content.html_fetcher import (
    HtmlFetchSettings,
    fetch_html,
    FetchError,
)
from app.application.content.content_snapshot import (
    save_snapshot,
    load_snapshot,
    get_snapshot_path,
    SnapshotWriteError,
)


# ── Result dataclass ─────────────────────────────────────────

@dataclass(frozen=True)
class SourceItemContentFetchResult:
    item_id: int
    status: str  # queued | fetching | fetched | skipped | failed | not_found
    message: str
    snapshot_path: str | None = None
    text_length: int | None = None
    error: str | None = None


# ── Content fetch status values ──────────────────────────────

class ContentFetchStatus:
    QUEUED = "queued"
    FETCHING = "fetching"
    FETCHED = "fetched"
    FAILED = "failed"
    SKIPPED = "skipped"


def _current_raw_status(item: SourceItem) -> str | None:
    """Read content_fetch_status from raw_metadata_json."""
    try:
        raw = json.loads(item.raw_metadata_json or "{}")
        return raw.get("content_fetch_status") if isinstance(raw, dict) else None
    except Exception:
        return None


def _write_status(
    item: SourceItem,
    db: Session,
    status: str,
    error: str | None = None,
    snapshot_path: str | None = None,
    text_length: int | None = None,
) -> None:
    """Write content_fetch_status into raw_metadata_json and commit."""
    try:
        raw = json.loads(item.raw_metadata_json or "{}")
    except Exception:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}

    raw["content_fetch_status"] = status
    raw["content_fetch_updated_at"] = datetime.utcnow().isoformat()
    if error:
        raw["content_fetch_error"] = error
    if snapshot_path:
        raw["content_snapshot_path"] = snapshot_path
    if text_length is not None:
        raw["content_text_length"] = text_length

    item.raw_metadata_json = json.dumps(raw, ensure_ascii=False)
    db.commit()


def fetch_source_item_content(
    db: Session,
    item_id: int,
    *,
    force: bool = False,
) -> SourceItemContentFetchResult:
    """Fetch HTML content for a SourceItem and save a snapshot.

    This function does NOT call any LLM.
    """
    # Step 1: Find item
    item = db.query(SourceItem).filter(SourceItem.id == item_id).first()
    if item is None:
        return SourceItemContentFetchResult(
            item_id=item_id,
            status="not_found",
            message=f"条目 {item_id} 不存在。",
        )

    # Step 2: Check URL
    if not item.url:
        _write_status(item, db, ContentFetchStatus.SKIPPED, error="no_url")
        return SourceItemContentFetchResult(
            item_id=item_id,
            status=ContentFetchStatus.SKIPPED,
            message="该条目没有 URL，已跳过。",
        )

    # Step 3: Check existing status (skip if already fetched and not forced)
    current_status = _current_raw_status(item)
    if current_status == ContentFetchStatus.FETCHED and not force:
        # Check if snapshot still exists
        existing_path = get_snapshot_path(item_id)
        if existing_path.exists():
            snapshot = load_snapshot(item_id)
            return SourceItemContentFetchResult(
                item_id=item_id,
                status=ContentFetchStatus.FETCHED,
                message="该条目正文已于此前获取，无需重复抓取。",
                snapshot_path=str(existing_path),
                text_length=snapshot.get("text_length") if snapshot else None,
            )

    # Step 4: Set status to fetching
    _write_status(item, db, ContentFetchStatus.FETCHING)

    # Step 5: Fetch HTML
    settings = HtmlFetchSettings.from_env()
    result = fetch_html(item.url, settings=settings)

    # Step 6: Handle fetch failure
    if result.status == "failed":
        _write_status(item, db, ContentFetchStatus.FAILED, error=result.error)
        return SourceItemContentFetchResult(
            item_id=item_id,
            status=ContentFetchStatus.FAILED,
            message=f"获取失败：{result.error}。",
            error=result.error,
        )

    if result.status == "skipped":
        _write_status(item, db, ContentFetchStatus.SKIPPED, error=result.error)
        return SourceItemContentFetchResult(
            item_id=item_id,
            status=ContentFetchStatus.SKIPPED,
            message=f"已跳过：{result.error}。",
            error=result.error,
        )

    # Step 7: Save snapshot
    snapshot_path = save_snapshot(item_id, result)
    if snapshot_path is None:
        _write_status(item, db, ContentFetchStatus.FAILED, error=SnapshotWriteError.WRITE_FAILED)
        return SourceItemContentFetchResult(
            item_id=item_id,
            status=ContentFetchStatus.FAILED,
            message="快照保存失败。",
            error=SnapshotWriteError.WRITE_FAILED,
        )

    # Step 8: Mark as fetched
    _write_status(
        item, db, ContentFetchStatus.FETCHED,
        snapshot_path=str(snapshot_path),
        text_length=len(result.text) if result.text else 0,
    )

    return SourceItemContentFetchResult(
        item_id=item_id,
        status=ContentFetchStatus.FETCHED,
        message="HTML 正文获取成功。",
        snapshot_path=str(snapshot_path),
        text_length=len(result.text) if result.text else 0,
    )
