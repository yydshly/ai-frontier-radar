"""Persisted 'last daily-cycle run' marker (runtime JSON).

The daily-cycle orchestration records when the pipeline last completed so that
(a) a multi-day offline gap can be detected for catch-up framing (design §6.8),
and (b) per-day history can mark days the cycle never ran as '未运行'.

Stored as a small JSON file colocated with the daily-report runtime dir (not the
DB). Writes are atomic (temp + rename).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.application.radar.daily_report_store import get_daily_report_runtime_dir


def _state_path(root_dir: Path | None = None) -> Path:
    return get_daily_report_runtime_dir(root_dir) / "daily_cycle_state.json"


def get_last_cycle_run(root_dir: Path | None = None) -> datetime | None:
    """Return when the daily cycle last completed (naive UTC), or None."""
    path = _state_path(root_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = data.get("last_run_at")
        return datetime.fromisoformat(raw) if raw else None
    except (ValueError, OSError, json.JSONDecodeError):
        return None


def set_last_cycle_run(
    now: datetime | None = None,
    *,
    root_dir: Path | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Record a completed cycle run (atomic write)."""
    now = now or datetime.utcnow()
    path = _state_path(root_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"last_run_at": now.isoformat()}
    if extra:
        payload.update(extra)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
