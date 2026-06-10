#!/usr/bin/env python3
"""
Manual stale running FetchRun recovery tool.

Marks FetchRun rows that are confirmed stuck in the ``running`` state (stale)
as ``failed``, so due-source computation stops reporting ``already_running``
and the affected sources can re-enter scheduling on the next radar update.

SAFETY MODEL — this is a human-confirmed recovery tool, NOT an automatic fixer:
- Default mode is DRY-RUN: it only prints what *would* change, writes nothing.
- The database is only written when ``--apply`` is passed explicitly.
- Before writing each row, the run is re-queried and re-checked: it must still
  be ``running`` AND still stale, otherwise it is skipped.
- It never triggers fetches, never re-schedules background work, never calls
  LLM services, and never touches SourceItem / InsightCard rows.

State semantics: a recovered run gets ``status="failed"`` plus an
``error_message`` carrying a ``[stale-timeout]`` marker. We deliberately reuse
the existing ``failed`` status (not a new ``failed_timeout`` enum) so existing
pages, stats, styles, and filters keep recognising it.

Usage:
    python scripts/mark_stale_fetch_runs_failed.py
    python scripts/mark_stale_fetch_runs_failed.py --apply
    python scripts/mark_stale_fetch_runs_failed.py --threshold-minutes 120
    python scripts/mark_stale_fetch_runs_failed.py --source-key openai_news
    python scripts/mark_stale_fetch_runs_failed.py --run-id 123
    python scripts/mark_stale_fetch_runs_failed.py --limit 10
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Default cap on rows processed per run (applies to both dry-run and apply).
DEFAULT_LIMIT = 20


def _format_dt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _is_stale_running(run, *, now, threshold_minutes):
    """Return (is_stale, age_minutes, reason) for a FetchRun row.

    Mirrors the logic in app.application.sources.stale_runs so the apply path
    can re-confirm staleness independently right before writing.
    """
    if run is None or run.status != "running":
        return (False, None, None)
    started_at = run.started_at
    if started_at is None:
        return (True, None, "missing_started_at")
    age_minutes = int((now - started_at).total_seconds() // 60)
    if age_minutes > threshold_minutes:
        return (True, age_minutes, "running_too_long")
    return (False, age_minutes, None)


def _build_stale_error_message(age_minutes, threshold_minutes) -> str:
    age_str = age_minutes if age_minutes is not None else "unknown"
    return (
        f"[stale-timeout] Marked failed by manual stale recovery after "
        f"{age_str} minutes running. threshold={threshold_minutes}."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manual stale running FetchRun recovery (dry-run by default)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write to the database. Without this flag the script is dry-run.",
    )
    parser.add_argument(
        "--threshold-minutes",
        type=int,
        default=None,
        metavar="N",
        help="Override stale threshold in minutes (default from env / 120).",
    )
    parser.add_argument(
        "--source-key",
        type=str,
        default=None,
        metavar="KEY",
        help="Only process stale running runs for this source_key.",
    )
    parser.add_argument(
        "--run-id",
        type=int,
        default=None,
        metavar="ID",
        help="Only process this FetchRun id (must still be running and stale).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        metavar="N",
        help=f"Max rows to process this run (default {DEFAULT_LIMIT}).",
    )
    args = parser.parse_args()

    apply = bool(args.apply)

    try:
        from app.db import SessionLocal
        from app.models import FetchRun
        from app.application.sources.stale_runs import (
            build_stale_fetch_run_report,
            get_stale_running_threshold_minutes,
            MIN_STALE_RUNNING_MINUTES,
            MAX_STALE_RUNNING_MINUTES,
        )
    except Exception as e:
        print(f"[ERROR] Failed to import required modules: {e}")
        sys.exit(1)

    # ── Parameter validation (must run before DB session creation) ──────────
    # Explicit --threshold-minutes / --limit must be inside the safe range.
    # This recovery tool writes to the DB; explicit user input should fail fast
    # rather than silently snap to a default.
    if args.threshold_minutes is not None:
        if (
            args.threshold_minutes < MIN_STALE_RUNNING_MINUTES
            or args.threshold_minutes > MAX_STALE_RUNNING_MINUTES
        ):
            print(
                f"[ERROR] --threshold-minutes must be between "
                f"{MIN_STALE_RUNNING_MINUTES} and {MAX_STALE_RUNNING_MINUTES}."
            )
            sys.exit(2)
    if args.limit is not None and args.limit < 1:
        print("[ERROR] --limit must be >= 1.")
        sys.exit(2)

    now = datetime.utcnow()
    if args.threshold_minutes is not None:
        threshold_minutes = args.threshold_minutes
    else:
        threshold_minutes = get_stale_running_threshold_minutes()

    print("Stale FetchRun recovery")
    print(f"mode: {'APPLY' if apply else 'DRY-RUN'}")
    print(f"threshold_minutes: {threshold_minutes}")

    db = SessionLocal()
    try:
        report = build_stale_fetch_run_report(
            db, now=now, threshold_minutes=threshold_minutes
        )

        # Filter the report's stale runs by the requested targets.
        selected = list(report.stale_runs)
        if args.source_key is not None:
            selected = [r for r in selected if r.source_key == args.source_key]
        if args.run_id is not None:
            selected = [r for r in selected if r.run_id == args.run_id]

        print(f"matched_stale_runs: {len(selected)}")

        if not selected:
            print("No stale running FetchRun matched the filters.")
            db.rollback()
            sys.exit(0)

        # Apply the limit (to both dry-run and apply).
        limited = selected[: args.limit] if args.limit is not None else selected
        print(f"limit: {args.limit}")

        if not apply:
            print(f"will_update: {len(limited)}")
            print()
            print("Planned updates:")
            for d in limited:
                age = d.age_minutes if d.age_minutes is not None else "—"
                print(
                    f"- run_id={d.run_id} source={d.source_key} "
                    f"age_minutes={age} status running -> failed"
                )
            print()
            print(
                "No database changes were made. "
                "Re-run with --apply to update these rows."
            )
            db.rollback()
            sys.exit(0)

        # APPLY path: re-confirm each row is still running AND still stale.
        updated = 0
        skipped = 0
        updated_rows = []
        for d in limited:
            run = db.query(FetchRun).filter(FetchRun.id == d.run_id).first()
            if run is None:
                skipped += 1
                continue
            if run.status != "running":
                skipped += 1
                continue
            is_stale, age_minutes, _reason = _is_stale_running(
                run, now=now, threshold_minutes=threshold_minutes
            )
            if not is_stale:
                skipped += 1
                continue

            run.status = "failed"
            run.finished_at = now
            run.error_message = _build_stale_error_message(age_minutes, threshold_minutes)
            if hasattr(run, "updated_at"):
                run.updated_at = now
            updated += 1
            updated_rows.append((run.id, run.source_key))

        db.commit()

        print(f"updated: {updated}")
        print(f"skipped: {skipped}")
        print()
        if updated_rows:
            print("Updated:")
            for run_id, source_key in updated_rows:
                print(f"- run_id={run_id} source={source_key} running -> failed")
        else:
            print("No rows were updated (all skipped on re-check).")
        sys.exit(0)
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Stale recovery failed: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
