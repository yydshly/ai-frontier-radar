"""Content snapshot persistence to runtime directory.

Snapshots are saved to runtime/content_snapshots/ as JSON files.
runtime/ is NOT committed to git.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from app.application.content.html_fetcher import HtmlFetchResult


# ── Path helpers ─────────────────────────────────────────────

def get_runtime_content_dir() -> Path:
    """Return the runtime content snapshots directory, creating it if needed."""
    # Resolve relative to project root (parent of app/)
    project_root = Path(__file__).resolve().parent.parent.parent
    content_dir = project_root / "runtime" / "content_snapshots"
    content_dir.mkdir(parents=True, exist_ok=True)
    return content_dir


def get_snapshot_path(source_item_id: int) -> Path:
    """Return the snapshot file path for a given source_item_id."""
    return get_runtime_content_dir() / f"source_item_{source_item_id}.json"


# ── Save / load ─────────────────────────────────────────────

def save_snapshot(
    source_item_id: int,
    fetch_result: HtmlFetchResult,
    fetched_at: datetime | None = None,
) -> Path | None:
    """Save an HtmlFetchResult to a JSON snapshot file.

    Returns the Path if successful, None if write failed.
    """
    if fetched_at is None:
        fetched_at = datetime.utcnow()

    snapshot_data = {
        "source_item_id": source_item_id,
        "url": fetch_result.url,
        "final_url": fetch_result.final_url,
        "fetched_at": fetched_at.isoformat(),
        "http_status": fetch_result.http_status,
        "content_type": fetch_result.content_type,
        "title": fetch_result.title,
        "meta_description": fetch_result.meta_description,
        "text": fetch_result.text,
        "text_length": len(fetch_result.text) if fetch_result.text else 0,
        "status": fetch_result.status,
        "error": fetch_result.error,
    }

    path = get_snapshot_path(source_item_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot_data, f, ensure_ascii=False, indent=2)
        return path
    except Exception:
        return None


def load_snapshot(source_item_id: int) -> dict | None:
    """Load a snapshot dict by source_item_id. Returns None if not found."""
    path = get_snapshot_path(source_item_id)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def snapshot_exists(source_item_id: int) -> bool:
    """Return True if a snapshot file exists for this source_item_id."""
    return get_snapshot_path(source_item_id).exists()


# ── Snapshot status ─────────────────────────────────────────

class SnapshotWriteError:
    WRITE_FAILED = "snapshot_write_failed"


def get_snapshot_status_text(status: str | None, error: str | None, text_length: int | None) -> str:
    """Build a human-readable status description for a snapshot."""
    if status == "fetched":
        return f"已获取 ({text_length or 0} 字)"
    if status == "skipped":
        return f"已跳过：{error or '未知原因'}"
    if status == "failed":
        return f"获取失败：{error or '未知原因'}"
    if status == "queued":
        return "等待获取"
    return "未获取"
