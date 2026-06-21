"""Per-day finalization status sidecars (P2 reliability/visibility).

A day without a persisted report (e.g. ``no_input`` — no articles in the
period, or a generation failure) was previously *invisible*: the history index
only lists dates that produced a report, so a blank day silently disappeared.
This store records a lightweight status record for **every** finalization
attempt — including the blank/failed ones — so the history page can show
"数据不完整 / 当日无内容 / 生成失败" instead of an unexplained gap.

These sidecars are derived, disposable metadata (not the report itself); they
live under ``runtime/daily_reports/status/`` next to the reports.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from app.application.radar.daily_report_store import get_daily_report_runtime_dir

_DATE_LABEL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def get_daily_status_dir(root_dir: Path | None = None) -> Path:
    """Return ``runtime/daily_reports/status/`` (created if absent)."""
    path = get_daily_report_runtime_dir(root_dir) / "status"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_daily_status_path(date_label: str, root_dir: Path | None = None) -> Path:
    if not _DATE_LABEL_RE.fullmatch(date_label):
        raise ValueError("date_label must use YYYY-MM-DD")
    return get_daily_status_dir(root_dir) / f"daily_status_{date_label}.json"


def save_daily_status(
    date_label: str,
    status: str,
    *,
    item_count: int = 0,
    detail: str | None = None,
    root_dir: Path | None = None,
) -> dict[str, Any]:
    """Persist (overwrite) the finalization status for ``date_label``.

    ``status`` is the finalization outcome (e.g. ``finalized``, ``no_input``,
    ``no_report``, ``save_failed``, ``already_finalized``).
    """
    if not _DATE_LABEL_RE.fullmatch(date_label):
        raise ValueError("date_label must use YYYY-MM-DD")
    payload: dict[str, Any] = {
        "date_label": date_label,
        "status": str(status),
        "item_count": int(item_count or 0),
        "detail": detail,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    path = get_daily_status_path(date_label, root_dir)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return payload


def load_daily_status(
    date_label: str,
    root_dir: Path | None = None,
) -> dict[str, Any] | None:
    if not _DATE_LABEL_RE.fullmatch(date_label):
        return None
    path = get_daily_status_path(date_label, root_dir)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict) or payload.get("date_label") != date_label:
        return None
    return payload


def list_daily_status_dates(root_dir: Path | None = None) -> list[str]:
    """Date labels (YYYY-MM-DD) that have a status sidecar, newest first."""
    dates: list[str] = []
    for path in get_daily_status_dir(root_dir).glob("daily_status_*.json"):
        label = path.stem.replace("daily_status_", "", 1)
        if _DATE_LABEL_RE.fullmatch(label):
            dates.append(label)
    return sorted(dates, reverse=True)
