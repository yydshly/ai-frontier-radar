"""Runtime persistence for generated daily core reports."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from app.application.radar.daily_report import DailyReportResult


_DATE_LABEL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def get_daily_report_runtime_dir(root_dir: Path | None = None) -> Path:
    if root_dir is None:
        configured = os.getenv("DAILY_REPORT_RUNTIME_DIR", "").strip()
        root_dir = (
            Path(configured)
            if configured
            else Path(__file__).resolve().parents[3] / "runtime" / "daily_reports"
        )
    root_dir.mkdir(parents=True, exist_ok=True)
    return root_dir


def get_daily_report_path(date_label: str, root_dir: Path | None = None) -> Path:
    if not _DATE_LABEL_RE.fullmatch(date_label):
        raise ValueError("date_label must use YYYY-MM-DD")
    return get_daily_report_runtime_dir(root_dir) / f"daily_report_{date_label}.json"


def save_daily_report(
    result: DailyReportResult,
    *,
    root_dir: Path | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any] | None:
    """Persist a successfully generated report and return its stored payload."""
    if result.status != "generated":
        return None
    generated_at = generated_at or datetime.utcnow()
    payload: dict[str, Any] = {
        "status": result.status,
        "date_label": result.date_label,
        "input_item_count": result.input_item_count,
        "message": result.message,
        "title": result.title,
        "overview": result.overview,
        "highlights": list(result.highlights),
        "highlight_references": list(result.highlight_references),
        "generated_at": generated_at.isoformat(timespec="seconds"),
    }
    path = get_daily_report_path(result.date_label, root_dir)
    temp_path = path.with_suffix(".tmp")
    try:
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temp_path, path)
        return payload
    except (OSError, TypeError, ValueError):
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def load_daily_report(
    date_label: str,
    *,
    root_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Load and minimally validate one generated daily report."""
    try:
        path = get_daily_report_path(date_label, root_dir)
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None
    if payload.get("status") != "generated" or payload.get("date_label") != date_label:
        return None
    if not isinstance(payload.get("highlights"), list):
        return None
    references = payload.get("highlight_references", [])
    if not isinstance(references, list):
        return None
    payload["highlight_references"] = references
    if not isinstance(payload.get("input_item_count"), int):
        return None
    return payload
