#!/usr/bin/env python3
"""
V1.0-beta.2 Task 2 — CLI single-shot due-source scheduler (DRY-RUN ONLY).

Computes this cycle's due-source plan and prints a readable summary of which
sources are due / skipped / running / unsupported / missing, plus which sources
*would* be started if this were applied.

Default mode is DRY-RUN — strictly read-only:
- It only calls the read-only ``compute_due_sources()`` service.
- It does NOT create FetchRun rows.
- It does NOT schedule any background work or dispatch the fetch service.
- It does NOT trigger real fetches, LLM calls, summaries, or InsightCard generation.
- It does NOT write to the database.

``--apply`` (Task 3A) executes ONLY ``plan.due`` sources, and only behind two
explicit safety gates:
- ``RADAR_SCHEDULER_ENABLED=true`` must be set (anti-misfire gate).
- ``AUTO_SUMMARY_MAX_PER_FETCH_RUN`` must be unset or ``0`` (no LLM summary).
  The fetch service runs synchronously (``background_tasks=None``), so disabling
  auto summary up front is what keeps ``--apply`` from triggering LLM work.
When ``plan.due`` is empty, ``--apply`` is a safe no-op (no FetchRun created).
It never processes skipped / running / unsupported / missing, and never performs
stale recovery.

Usage:
    python scripts/run_due_sources_once.py
    python scripts/run_due_sources_once.py --max-sources 3
    python scripts/run_due_sources_once.py --show-skipped
    python scripts/run_due_sources_once.py --apply
    RADAR_SCHEDULER_ENABLED=true AUTO_SUMMARY_MAX_PER_FETCH_RUN=0 \
        python scripts/run_due_sources_once.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CLI single-shot due-source scheduler (dry-run by default)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Execute due sources by creating FetchRun rows. Requires "
            "RADAR_SCHEDULER_ENABLED=true and AUTO_SUMMARY_MAX_PER_FETCH_RUN=0. "
            "Without this flag the script is dry-run."
        ),
    )
    parser.add_argument(
        "--max-sources",
        type=int,
        default=None,
        metavar="N",
        help="Cap on number of due sources this cycle (excess moved to skipped). N >= 1.",
    )
    parser.add_argument(
        "--show-skipped",
        action="store_true",
        help="Show skipped sources with reasons.",
    )
    parser.add_argument(
        "--show-running",
        action="store_true",
        help="Show running sources.",
    )
    parser.add_argument(
        "--show-unsupported",
        action="store_true",
        help="Show unsupported-strategy sources.",
    )
    parser.add_argument(
        "--show-missing",
        action="store_true",
        help="Show sources missing a DB record.",
    )
    return parser.parse_args(argv)


def _validate_args(args: argparse.Namespace) -> int | None:
    """Return an exit code if args are invalid, else None."""
    if args.max_sources is not None and args.max_sources < 1:
        print("[ERROR] --max-sources must be >= 1.")
        return 2
    return None


def _print_bucket(title: str, decisions) -> None:
    print(f"{title}:")
    if not decisions:
        print("  none")
        return
    for d in decisions:
        print(f"  - {d.source_key} (reason={d.reason})")


def _scheduler_enabled_for_apply() -> bool:
    return os.getenv("RADAR_SCHEDULER_ENABLED", "").lower() == "true"


def _ensure_apply_safety(args: argparse.Namespace) -> int | None:
    """Enforce the two explicit safety gates for --apply. Returns exit code or None.

    Gate 1: RADAR_SCHEDULER_ENABLED=true (anti-misfire).
    Gate 2: AUTO_SUMMARY_MAX_PER_FETCH_RUN must be unset or "0" (no LLM summary).
            If unset, default it to "0" so the synchronous fetch won't summarize.
    """
    if not args.apply:
        return None

    if not _scheduler_enabled_for_apply():
        print("[ERROR] --apply requires RADAR_SCHEDULER_ENABLED=true.")
        return 2

    raw = os.getenv("AUTO_SUMMARY_MAX_PER_FETCH_RUN")
    if raw is None:
        os.environ["AUTO_SUMMARY_MAX_PER_FETCH_RUN"] = "0"
    elif raw != "0":
        print("[ERROR] --apply requires AUTO_SUMMARY_MAX_PER_FETCH_RUN=0 in Task 3A.")
        return 2

    return None


def _print_plan_summary(plan, args: argparse.Namespace, header: str) -> None:
    print(f"[run_due_sources_once] {header}")
    if header == "APPLY":
        print("RADAR_SCHEDULER_ENABLED=true")
        print(f"AUTO_SUMMARY_MAX_PER_FETCH_RUN={os.getenv('AUTO_SUMMARY_MAX_PER_FETCH_RUN')}")
    print(f"total_configured={plan.total_configured}")
    print(f"due={plan.due_count}")
    print(f"skipped={plan.skipped_count}")
    print(f"running={plan.running_count}")
    print(f"unsupported={plan.unsupported_count}")
    print(f"missing={plan.missing_count}")
    print()

    print("would_start:")
    if plan.due:
        for d in plan.due:
            print(f"  - {d.source_key}")
    else:
        print("  none")
    print()

    reason_summary = Counter(d.reason for d in plan.skipped)
    print("reason_summary:")
    if reason_summary:
        for reason, count in sorted(reason_summary.items()):
            print(f"  {reason}={count}")
    else:
        print("  none")

    # Optional detail buckets.
    if args.show_skipped:
        print()
        _print_bucket("skipped_detail", plan.skipped)
    if args.show_running:
        print()
        _print_bucket("running_detail", plan.running)
    if args.show_unsupported:
        print()
        _print_bucket("unsupported_detail", plan.unsupported)
    if args.show_missing:
        print()
        _print_bucket("missing_detail", plan.missing)


def _run_dry_run(plan, args: argparse.Namespace) -> int:
    _print_plan_summary(plan, args, "DRY-RUN")
    print()
    print(
        "No FetchRun created. Use --apply with RADAR_SCHEDULER_ENABLED=true "
        "to execute due sources."
    )
    return 0


def _run_apply(plan, args: argparse.Namespace, db) -> int:
    _print_plan_summary(plan, args, "APPLY")
    print()

    if not plan.due:
        print("apply_result:")
        print("  started=0")
        print("  already_running=0")
        print("  failed_to_start=0")
        print()
        print("No due sources to start.")
        return 0

    # Only processes plan.due. Never touches skipped / running / unsupported /
    # missing. background_tasks=None runs the fetch synchronously.
    from app.application.sources.background_fetch import SourceFetchBackgroundService
    from app.models import FetchRun

    service = SourceFetchBackgroundService()
    started = []
    already_running = []
    failed_to_start = []

    for decision in plan.due:
        result = service.enqueue_source(decision.source_key, background_tasks=None)
        if result.status == "running" and result.accepted:
            started.append((decision.source_key, result.run_id))
        elif result.status == "already_running":
            already_running.append((decision.source_key, result.run_id))
        else:
            failed_to_start.append((decision.source_key, result.message))

    print("apply_result:")
    print(f"  started={len(started)}")
    print(f"  already_running={len(already_running)}")
    print(f"  failed_to_start={len(failed_to_start)}")

    if started:
        print()
        print("started_runs:")
        for source_key, run_id in started:
            run = db.query(FetchRun).filter(FetchRun.id == run_id).first()
            final_status = run.status if run else "unknown"
            if run is not None:
                print(
                    f"  - {source_key} run_id={run_id} final_status={final_status} "
                    f"items_found={run.items_found} items_new={run.items_new} "
                    f"items_updated={run.items_updated} items_failed={run.items_failed}"
                )
            else:
                print(f"  - {source_key} run_id={run_id} final_status={final_status}")

    if already_running:
        print()
        print("already_running_runs:")
        for source_key, run_id in already_running:
            print(f"  - {source_key} run_id={run_id}")

    if failed_to_start:
        print()
        print("failed_to_start_runs:")
        for source_key, message in failed_to_start:
            print(f"  - {source_key} message={message}")

    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    invalid = _validate_args(args)
    if invalid is not None:
        return invalid

    gate = _ensure_apply_safety(args)
    if gate is not None:
        return gate

    try:
        from app.db import SessionLocal
        from app.application.sources.due_sources import compute_due_sources
    except Exception as e:
        print(f"[ERROR] Failed to import required modules: {e}")
        return 1

    db = SessionLocal()
    try:
        plan = compute_due_sources(db, max_sources=args.max_sources)
        if args.apply:
            return _run_apply(plan, args, db)
        return _run_dry_run(plan, args)
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
