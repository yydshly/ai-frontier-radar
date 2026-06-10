#!/usr/bin/env python3
"""
Read-only diagnostic script for stale running FetchRun rows.

Identifies FetchRun rows stuck in the ``running`` state for longer than a
configurable threshold. These cause due-source computation to keep reporting
``already_running`` and silently skip the affected sources.

Strictly read-only: never modifies FetchRun status (no auto-fail, no retry),
never writes to the database, never triggers fetches or schedules background
tasks, never calls LLM services, and never accesses the network.

Usage:
    python scripts/check_stale_fetch_runs.py
    python scripts/check_stale_fetch_runs.py --threshold-minutes 60
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _format_dt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stale running FetchRun diagnostic (read-only)"
    )
    parser.add_argument(
        "--threshold-minutes",
        type=int,
        default=None,
        metavar="N",
        help="Override stale threshold in minutes (default from env / 120)",
    )
    args = parser.parse_args()

    print("Stale FetchRun check")

    try:
        from app.db import SessionLocal
        from app.application.sources.stale_runs import build_stale_fetch_run_report
    except Exception as e:
        print(f"[ERROR] Failed to import required modules: {e}")
        sys.exit(1)

    db = SessionLocal()
    try:
        report = build_stale_fetch_run_report(
            db,
            now=datetime.utcnow(),
            threshold_minutes=args.threshold_minutes,
        )
    except Exception as e:
        print(f"[ERROR] Failed to build stale fetch run report: {e}")
        sys.exit(1)
    finally:
        db.close()

    print(f"threshold_minutes: {report.threshold_minutes}")
    print(f"total_running: {report.total_running}")
    print(f"stale_count: {report.stale_count}")
    affected = ", ".join(report.affected_source_keys) if report.affected_source_keys else "—"
    print(f"affected_sources: {affected}")
    print()

    if report.stale_runs:
        print("Stale runs:")
        for r in report.stale_runs:
            age = r.age_minutes if r.age_minutes is not None else "—"
            print(
                f"- run_id={r.run_id} source={r.source_key} "
                f"age_minutes={age} reason={r.reason} "
                f"started_at={_format_dt(r.started_at)}"
            )
    else:
        print("No stale running FetchRun detected.")

    sys.exit(0)


if __name__ == "__main__":
    main()
