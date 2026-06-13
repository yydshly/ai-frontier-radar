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
    append_daily_cycle_log,
    save_daily_cycle_run_report,
)


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
        "command": command,
    }


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
    result = None
    exit_code = 0

    try:
        db = SessionLocal()
        try:
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
    except Exception as exc:
        # Unhandled exception — build a failed report.
        import sys as _sys
        print(f"[ERROR] Unhandled exception in run_daily_cycle: {exc}", file=_sys.stderr)
        finished_at = datetime.now()
        exit_code = 1
        # Synthesise a minimal DailyCycleResult so the report has the right shape.
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
            "run_id": started_at.strftime("%Y%m%d_%H%M%S"),
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

    # Persist the JSON report (both <run_id>.json and latest.json).
    save_daily_cycle_run_report(report)

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

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
