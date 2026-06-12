"""Run the daily cycle: fetch increment → summarize → report → (opt) audio.

Intended to be invoked by an external scheduler (Windows Task Scheduler / cron)
at the daily anchor (08:00). Dry-run by default; --apply performs the cycle.

Usage:
    python scripts/run_daily_cycle.py                 # dry-run (no side effects)
    python scripts/run_daily_cycle.py --apply          # fetch + summarize + report
    python scripts/run_daily_cycle.py --apply --audio   # also synthesize narration
    python scripts/run_daily_cycle.py --apply --no-fetch # skip fetch (summarize+report only)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

for _s in (sys.stdout, sys.stderr):  # UTF-8 safe on Windows GBK consoles
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from app.db import SessionLocal  # noqa: E402
from app.application.radar.daily_cycle import run_daily_cycle  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the daily radar cycle.")
    parser.add_argument("--apply", action="store_true", help="perform the cycle (default: dry-run)")
    parser.add_argument("--no-fetch", action="store_true", help="skip the increment fetch step")
    parser.add_argument("--no-summary", action="store_true", help="skip the summarize step")
    parser.add_argument("--no-report", action="store_true", help="skip the report step")
    parser.add_argument("--audio", action="store_true", help="also synthesize the report narration (TTS)")
    parser.add_argument("--max-sources", type=int, default=50, help="cap on due sources fetched")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = run_daily_cycle(
            db,
            dry_run=not args.apply,
            do_fetch=not args.no_fetch,
            do_summary=not args.no_summary,
            do_report=not args.no_report,
            do_audio=args.audio,
            max_sources=args.max_sources,
        )
    finally:
        db.close()

    print("=" * 60)
    print(f"Daily cycle ({'DRY-RUN' if result.dry_run else 'APPLY'})")
    print("=" * 60)
    for step in result.steps:
        print(f"  - {step}")
    print(f"  report_status: {result.report_status}")
    print(f"  audio_status:  {result.audio_status}")
    if result.errors:
        print("  errors:")
        for e in result.errors:
            print(f"    ! {e}")
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
