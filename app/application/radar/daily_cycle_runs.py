"""Runtime persistence for daily-cycle run execution reports.

Each invocation of ``scripts/run_daily_cycle.py`` produces a structured JSON
report stored under ``runtime/daily_cycle_runs/``:

- ``<run_id>.json``   — historical record, e.g. ``20260613_080500.json``
- ``latest.json``     — always points to the most recent run

The module also provides a ``logs/daily_cycle.log`` text log for human
troubleshooting, appended on every run.

These files are intended for consumption by a future local-control GUI or
status dashboard — not by the main application logic.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

# Reuse the existing runtime root detection from daily_report_store.
from app.application.radar.daily_report_store import get_daily_report_runtime_dir

_RUN_ID_RE = re.compile(r"^\d{8}_\d{6}$")


def _get_runtime_root(root_dir: str | Path | None = None) -> Path:
    """Return the project root (the directory that contains ``runtime/``)."""
    if root_dir is not None:
        return Path(root_dir).resolve()
    configured = os.getenv("DAILY_CYCLE_RUNS_ROOT_DIR", "").strip()
    if configured:
        return Path(configured).resolve()
    # Colocate with other daily-report runtime artefacts.
    # get_daily_report_runtime_dir() returns <project>/runtime/daily_reports,
    # so two levels up gives the project root.
    return get_daily_report_runtime_dir() / ".." / ".."


def get_daily_cycle_runs_dir(root_dir: str | Path | None = None) -> Path:
    """Return the ``runtime/daily_cycle_runs/`` directory (created if absent)."""
    path = _get_runtime_root(root_dir) / "runtime" / "daily_cycle_runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_daily_cycle_latest_path(root_dir: str | Path | None = None) -> Path:
    """Return ``runtime/daily_cycle_runs/latest.json``."""
    return get_daily_cycle_runs_dir(root_dir) / "latest.json"


def get_daily_cycle_run_path(run_id: str, root_dir: str | Path | None = None) -> Path:
    """Return ``runtime/daily_cycle_runs/<run_id>.json``."""
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError(
            f"run_id must match YYYYMMDD_HHMMSS, got: {run_id!r}"
        )
    return get_daily_cycle_runs_dir(root_dir) / f"{run_id}.json"


def get_daily_cycle_log_path(root_dir: str | Path | None = None) -> Path:
    """Return ``logs/daily_cycle.log`` alongside the project root."""
    log_dir = _get_runtime_root(root_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "daily_cycle.log"


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> bool:
    """Write ``payload`` to ``path`` using a temp-file + replace (atomic on POSIX)."""
    temp = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temp, path)
        return True
    except (OSError, TypeError, ValueError) as exc:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        # Log but do not propagate — report saving must not crash the cycle.
        import sys
        print(f"[WARNING] Failed to write {path}: {exc}", file=sys.stderr)
        return False


def save_daily_cycle_run_report(
    report: dict[str, Any],
    *,
    root_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Persist ``report`` as ``<run_id>.json`` and update ``latest.json``.

    Returns the saved report dict on success, or a minimal failed report on error.
    The caller is responsible for adding ``run_id``, ``command``, ``started_at``,
    ``finished_at``, ``duration_seconds`` and other top-level fields.
    """
    run_id = report.get("run_id")
    if not run_id or not _RUN_ID_RE.fullmatch(run_id):
        import sys
        print(
            f"[WARNING] save_daily_cycle_run_report called without a valid run_id; "
            f"skipping file writes.",
            file=sys.stderr,
        )
        return report

    latest_path = get_daily_cycle_latest_path(root_dir)
    run_path = get_daily_cycle_run_path(run_id, root_dir)

    _write_json_atomic(run_path, report)
    _write_json_atomic(latest_path, report)

    return report


def load_latest_daily_cycle_run(
    *,
    root_dir: str | Path | None = None,
) -> dict[str, Any] | None:
    """Load and return the most recent run report from ``latest.json``.

    Returns ``None`` if the file does not exist or is corrupt.
    Does not raise — callers must handle gracefully.
    """
    try:
        path = get_daily_cycle_latest_path(root_dir)
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def append_daily_cycle_log(
    run_id: str,
    mode: str,
    command: str,
    started_at: str,
    finished_at: str | None,
    duration_seconds: int | None,
    exit_code: int,
    status: str,
    report_status: str,
    audio_status: str,
    steps: list[str],
    errors: list[str],
    *,
    root_dir: str | Path | None = None,
) -> None:
    """Append a human-readable run summary to ``logs/daily_cycle.log``.

    Uses ``started_at`` (not ``run_id`` alone) so the timestamp is unambiguous.
    """
    log_path = get_daily_cycle_log_path(root_dir)
    lines = [
        "=" * 60,
        f"Daily cycle {mode.upper()} {started_at}",
        "=" * 60,
        f"run_id:           {run_id}",
        f"command:          {command}",
        f"started_at:       {started_at}",
        f"finished_at:      {finished_at or 'N/A'}",
        f"duration_seconds: {duration_seconds if duration_seconds is not None else 'N/A'}",
        f"exit_code:        {exit_code}",
        f"status:           {status}",
        f"report_status:    {report_status}",
        f"audio_status:     {audio_status}",
        "steps:",
    ]
    for step in steps:
        lines.append(f"  - {step}")
    if errors:
        lines.append("errors:")
        for err in errors:
            lines.append(f"  ! {err}")
    else:
        lines.append("errors:        (none)")

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    except OSError as exc:
        import sys
        print(f"[WARNING] Failed to append to {log_path}: {exc}", file=sys.stderr)


# ─────────────────────────────────────────────────────────────────────────────
# Running status + live log helpers
#
# These files support a future "current run" observability view (e.g. the
# /local-status page and any local GUI launcher). They are NOT required for
# the main daily-cycle business logic.
# ─────────────────────────────────────────────────────────────────────────────


def get_daily_cycle_running_path(root_dir: str | Path | None = None) -> Path:
    """Return ``runtime/daily_cycle_runs/running.json`` (a transient marker)."""
    return get_daily_cycle_runs_dir(root_dir) / "running.json"


def get_daily_cycle_live_log_path(root_dir: str | Path | None = None) -> Path:
    """Return ``logs/daily_cycle.live.log`` (transient, appended while a run is in flight)."""
    return _get_runtime_root(root_dir) / "logs" / "daily_cycle.live.log"


def save_daily_cycle_running_status(
    status: dict[str, Any],
    *,
    root_dir: str | Path | None = None,
) -> bool:
    """Atomically write ``runtime/daily_cycle_runs/running.json``.

    Returns True on success, False on any error (never raises).
    """
    path = get_daily_cycle_running_path(root_dir)
    return _write_json_atomic(path, status)


def load_daily_cycle_running_status(
    *,
    root_dir: str | Path | None = None,
) -> dict[str, Any] | None:
    """Load ``runtime/daily_cycle_runs/running.json`` safely; return None on missing/corrupt."""
    try:
        path = get_daily_cycle_running_path(root_dir)
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def clear_daily_cycle_running_status(
    *,
    root_dir: str | Path | None = None,
) -> bool:
    """Delete ``runtime/daily_cycle_runs/running.json`` if it exists.

    Returns True if file was deleted (or already absent), False on error.
    Never raises — failure to clear must not break the main flow.
    """
    try:
        path = get_daily_cycle_running_path(root_dir)
        if path.exists():
            path.unlink()
        return True
    except OSError as exc:
        import sys
        print(f"[WARNING] Failed to clear running.json: {exc}", file=sys.stderr)
        return False


def append_daily_cycle_live_log(
    message: str,
    *,
    root_dir: str | Path | None = None,
) -> None:
    """Append a single line to ``logs/daily_cycle.live.log`` (UTF-8).

    Silently swallows OSError so logging never breaks the main flow.
    """
    try:
        path = get_daily_cycle_live_log_path(root_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(message.rstrip("\n") + "\n")
    except OSError as exc:
        import sys
        print(f"[WARNING] Failed to append to live log: {exc}", file=sys.stderr)
