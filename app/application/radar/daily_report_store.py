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
_VERSION_ID_RE = re.compile(r"^\d{8}T\d{12}Z$")


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


def get_final_daily_report_dir(root_dir: Path | None = None) -> Path:
    return get_daily_report_runtime_dir(root_dir) / "final"


def get_final_daily_report_path(
    date_label: str,
    root_dir: Path | None = None,
) -> Path:
    if not _DATE_LABEL_RE.fullmatch(date_label):
        raise ValueError("date_label must use YYYY-MM-DD")
    return get_final_daily_report_dir(root_dir) / f"daily_report_{date_label}.json"


def list_daily_report_dates(root_dir: Path | None = None) -> list[str]:
    """Return the date labels (YYYY-MM-DD) that have a persisted report, newest
    first. Backs the per-day history index."""
    runtime_dir = get_daily_report_runtime_dir(root_dir)
    dates: list[str] = []
    for path in runtime_dir.glob("daily_report_*.json"):
        label = path.stem.replace("daily_report_", "", 1)
        if _DATE_LABEL_RE.fullmatch(label):
            dates.append(label)
    return sorted(dates, reverse=True)


def list_final_daily_report_dates(root_dir: Path | None = None) -> list[str]:
    dates: list[str] = []
    for path in get_final_daily_report_dir(root_dir).glob("daily_report_*.json"):
        label = path.stem.replace("daily_report_", "", 1)
        if _DATE_LABEL_RE.fullmatch(label):
            dates.append(label)
    return sorted(dates, reverse=True)


def get_daily_report_history_dir(
    date_label: str,
    root_dir: Path | None = None,
) -> Path:
    if not _DATE_LABEL_RE.fullmatch(date_label):
        raise ValueError("date_label must use YYYY-MM-DD")
    path = get_daily_report_runtime_dir(root_dir) / "history" / date_label
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_daily_report_version_path(
    date_label: str,
    version_id: str,
    root_dir: Path | None = None,
) -> Path:
    if not _VERSION_ID_RE.fullmatch(version_id):
        raise ValueError("invalid daily report version")
    return get_daily_report_history_dir(date_label, root_dir) / f"{version_id}.json"


def _write_payload(path: Path, payload: dict[str, Any]) -> bool:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temp_path, path)
        return True
    except (OSError, TypeError, ValueError):
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def _validate_payload(
    payload: Any,
    date_label: str,
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("status") != "generated" or payload.get("date_label") != date_label:
        return None
    if not isinstance(payload.get("highlights"), list):
        return None
    references = payload.get("highlight_references", [])
    if not isinstance(references, list):
        return None
    if not isinstance(payload.get("input_item_count"), int):
        return None
    payload["highlight_references"] = references
    return payload


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
    version_id = generated_at.strftime("%Y%m%dT%H%M%S%fZ")
    payload: dict[str, Any] = {
        "status": result.status,
        "date_label": result.date_label,
        "input_item_count": result.input_item_count,
        "message": result.message,
        "title": result.title,
        "overview": result.overview,
        "highlights": list(result.highlights),
        "highlight_references": list(result.highlight_references),
        "input_fingerprint": result.input_fingerprint,
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "version_id": version_id,
    }
    version_path = get_daily_report_version_path(
        result.date_label,
        version_id,
        root_dir,
    )
    latest_path = get_daily_report_path(result.date_label, root_dir)
    if not _write_payload(version_path, payload):
        return None
    if not _write_payload(latest_path, payload):
        try:
            version_path.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    return payload


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

    return _validate_payload(payload, date_label)


def save_final_daily_report(
    result: DailyReportResult,
    *,
    articles: list[dict[str, Any]],
    window_start: datetime,
    window_end: datetime,
    root_dir: Path | None = None,
    finalized_at: datetime | None = None,
    summary_status: str = "completed",
    audio_status: str = "pending",
) -> dict[str, Any] | None:
    """Persist one immutable-by-default formal report for an anchor period."""
    if result.status != "generated":
        return None
    path = get_final_daily_report_path(result.date_label, root_dir)
    existing = load_final_daily_report(result.date_label, root_dir=root_dir)
    if existing is not None:
        return existing

    finalized_at = finalized_at or datetime.utcnow()
    version_id = finalized_at.strftime("%Y%m%dT%H%M%S%fZ")
    payload: dict[str, Any] = {
        "status": result.status,
        "report_kind": "final",
        "date_label": result.date_label,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "finalized_at": finalized_at.isoformat(timespec="seconds"),
        "generated_at": finalized_at.isoformat(timespec="seconds"),
        "version_id": version_id,
        "input_item_count": result.input_item_count,
        "message": result.message,
        "title": result.title,
        "overview": result.overview,
        "highlights": list(result.highlights),
        "highlight_references": list(result.highlight_references),
        "input_fingerprint": result.input_fingerprint,
        "summary_status": summary_status,
        "audio_status": audio_status,
        "articles": articles,
    }
    return payload if _write_payload(path, payload) else None


def load_final_daily_report(
    date_label: str,
    *,
    root_dir: Path | None = None,
) -> dict[str, Any] | None:
    try:
        path = get_final_daily_report_path(date_label, root_dir)
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    validated = _validate_payload(payload, date_label)
    if validated is None or validated.get("report_kind") != "final":
        return None
    if not isinstance(validated.get("articles"), list):
        return None
    return validated


def update_final_daily_report(
    date_label: str,
    updates: dict[str, Any],
    *,
    root_dir: Path | None = None,
) -> dict[str, Any] | None:
    payload = load_final_daily_report(date_label, root_dir=root_dir)
    if payload is None:
        return None
    payload.update(updates)
    path = get_final_daily_report_path(date_label, root_dir)
    return payload if _write_payload(path, payload) else None


def load_daily_report_version(
    date_label: str,
    version_id: str,
    *,
    root_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Load one immutable generated-report version."""
    try:
        path = get_daily_report_version_path(date_label, version_id, root_dir)
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return _validate_payload(payload, date_label)


def list_daily_report_versions(
    date_label: str,
    *,
    root_dir: Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return newest report versions, with legacy-latest fallback."""
    try:
        history_dir = get_daily_report_history_dir(date_label, root_dir)
    except ValueError:
        return []

    versions: list[dict[str, Any]] = []
    for path in history_dir.glob("*.json"):
        try:
            payload = _validate_payload(
                json.loads(path.read_text(encoding="utf-8")),
                date_label,
            )
        except (OSError, json.JSONDecodeError):
            payload = None
        if payload is not None:
            versions.append(payload)

    versions.sort(
        key=lambda value: str(value.get("generated_at") or ""),
        reverse=True,
    )
    if versions:
        return versions[:max(1, limit)]

    legacy = load_daily_report(date_label, root_dir=root_dir)
    return [legacy] if legacy is not None else []
