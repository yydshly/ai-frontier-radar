"""Run the daily cycle: fetch increment → summarize → report → (opt) audio.

Intended to be invoked by an external scheduler (Windows Task Scheduler / cron)
at the daily anchor (08:00). Dry-run by default; --apply performs the cycle.

Usage:
    python scripts/run_daily_cycle.py                 # dry-run (no side effects)
    python scripts/run_daily_cycle.py --apply          # finalize + audio + live processing
    python scripts/run_daily_cycle.py --apply --no-audio # skip formal narration
    python scripts/run_daily_cycle.py --apply --no-fetch # skip fetch (summarize+report only)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

for _s in (sys.stdout, sys.stderr):  # UTF-8 safe on Windows GBK consoles
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from app.db import SessionLocal  # noqa: E402
from app.application.radar.daily_cycle import run_daily_cycle  # noqa: E402
from app.application.radar.daily_cycle_runs import (  # noqa: E402
    append_daily_cycle_live_log,
    append_daily_cycle_log,
    clear_daily_cycle_running_status,
    load_daily_cycle_running_status,
    save_daily_cycle_running_status,
    save_daily_cycle_run_report,
)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _emit_live(tag: str, message: str) -> None:
    """Print to console (flush) and append to logs/daily_cycle.live.log."""
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{tag}] {message}"
    print(line, flush=True)
    append_daily_cycle_live_log(line)


def _build_report(
    result,
    mode: str,
    command: str,
    started_at: datetime,
    finished_at: datetime,
    exit_code: int,
) -> dict:
    """Assemble the structured run report dict from cycle result + timing."""
    return {
        "run_id": started_at.strftime("%Y%m%d_%H%M%S"),
        "mode": mode,
        "status": "success" if exit_code == 0 else "failed",
        "exit_code": exit_code,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": int((finished_at - started_at).total_seconds()),
        "fetch_due": result.fetch_due,
        "fetch_started": result.fetch_started,
        "summary_targets": result.summary_targets,
        "summary_completed": result.summary_completed,
        "report_status": result.report_status,
        "audio_status": result.audio_status,
        "finalized_dates": list(result.finalized_dates),
        "steps": list(result.steps),
        "errors": list(result.errors),
        "log_path": "logs/daily_cycle.log",
        "live_log_path": "logs/daily_cycle.live.log",
        "command": command,
    }


def _write_running(
    run_id: str,
    mode: str,
    started_at: datetime,
    current_step: str,
    command: str,
    errors: list[str] | None = None,
) -> None:
    """Persist runtime/daily_cycle_runs/running.json (best-effort)."""
    payload = {
        "run_id": run_id,
        "status": "failed" if (errors and len(errors) > 0 and current_step == "failed") else "running",
        "mode": mode,
        "started_at": started_at.isoformat(),
        "updated_at": _now_iso(),
        "current_step": current_step,
        "command": command,
        "pid": os.getpid(),
        "live_log_path": "logs/daily_cycle.live.log",
        "errors": list(errors or []),
    }
    save_daily_cycle_running_status(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the daily radar cycle.")
    parser.add_argument("--apply", action="store_true", help="perform the cycle (default: dry-run)")
    parser.add_argument("--no-fetch", action="store_true", help="skip the increment fetch step")
    parser.add_argument("--no-summary", action="store_true", help="skip the summarize step")
    parser.add_argument("--no-report", action="store_true", help="skip the report step")
    parser.add_argument("--audio", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-audio", action="store_true", help="skip formal report narration")
    parser.add_argument("--max-sources", type=int, default=50, help="cap on due sources fetched")
    args = parser.parse_args()

    mode = "apply" if args.apply else "dry-run"
    command = " ".join(sys.argv)

    started_at = datetime.now()
    run_id = started_at.strftime("%Y%m%d_%H%M%S")
    result = None
    exit_code = 0

    # ── [START] emit immediately so users see something in the new window ──
    _emit_live("START", f"Daily cycle {mode} (run_id={run_id})")

    # ── Write running.json so /local-status and PS launcher can see it ──────
    _write_running(run_id, mode, started_at, "starting", command)
    _emit_live("STEP", "starting")

    try:
        _emit_live("STEP", "initializing_db")
        _write_running(run_id, mode, started_at, "initializing_db", command)
        db = SessionLocal()
        try:
            _emit_live("STEP", "running_cycle")
            _write_running(run_id, mode, started_at, "running_cycle", command)
            result = run_daily_cycle(
                db,
                dry_run=not args.apply,
                do_fetch=not args.no_fetch,
                do_summary=not args.no_summary,
                do_report=not args.no_report,
                do_audio=not args.no_audio,
                max_sources=args.max_sources,
            )
        finally:
            db.close()
        _emit_live("STEP", "running_cycle_done")
    except Exception as exc:
        _emit_live("ERROR", f"unhandled exception: {exc}")
        finished_at = datetime.now()
        exit_code = 1
        from app.application.radar.daily_cycle import DailyCycleResult
        result = DailyCycleResult(dry_run=not args.apply)
        result.errors.append(f"unhandled: {exc}")

    finished_at = datetime.now()

    # Print original console output (unchanged behaviour).
    print("=" * 60)
    print(f"Daily cycle ({'DRY-RUN' if (not args.apply) else 'APPLY'})")
    print("=" * 60)
    if result is not None:
        for step in result.steps:
            print(f"  - {step}")
        print(f"  report_status: {result.report_status}")
        print(f"  audio_status:  {result.audio_status}")
        if result.errors:
            print("  errors:")
            for e in result.errors:
                print(f"    ! {e}")

    if result is not None:
        exit_code = 1 if result.errors else 0

    # ── Build and persist structured report ──────────────────────────────
    if result is not None:
        report = _build_report(
            result,
            mode=mode,
            command=command,
            started_at=started_at,
            finished_at=finished_at,
            exit_code=exit_code,
        )
    else:
        # Should not reach here, but guard against None result.
        report = {
            "run_id": run_id,
            "mode": mode,
            "status": "failed",
            "exit_code": 1,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_seconds": int((finished_at - started_at).total_seconds()),
            "errors": ["result_was_none"],
            "command": command,
        }
        exit_code = 1

    _emit_live("STEP", "writing_report")
    _write_running(run_id, mode, started_at, "writing_report", command, errors=report.get("errors", []))

    # Persist the JSON report (both <run_id>.json and latest.json).
    save_daily_cycle_run_report(report)

    _emit_live("STEP", "appending_log")
    _write_running(run_id, mode, started_at, "appending_log", command, errors=report.get("errors", []))

    # Append human-readable text log.
    append_daily_cycle_log(
        run_id=report["run_id"],
        mode=mode,
        command=command,
        started_at=report["started_at"],
        finished_at=report["finished_at"],
        duration_seconds=report["duration_seconds"],
        exit_code=exit_code,
        status=report["status"],
        report_status=report.get("report_status", "unknown"),
        audio_status=report.get("audio_status", "unknown"),
        steps=report.get("steps", []),
        errors=report.get("errors", []),
    )

    if exit_code == 0:
        _emit_live("DONE", f"exit_code=0 status={report['status']}")
        _write_running(run_id, mode, started_at, "done", command, errors=[])
        # Clean up the running marker on success.
        clear_daily_cycle_running_status()
    else:
        _emit_live("ERROR", f"exit_code={exit_code} status={report['status']}")
        # Keep the running.json with status=failed so users can see the failure.
        _write_running(
            run_id,
            mode,
            started_at,
            "failed",
            command,
            errors=report.get("errors", []),
        )
        # Also set status="failed" explicitly in running.json.
        existing = load_daily_cycle_running_status() or {}
        existing["status"] = "failed"
        save_daily_cycle_running_status(existing)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
