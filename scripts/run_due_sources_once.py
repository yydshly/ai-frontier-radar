#!/usr/bin/env python3
"""
V1.0-beta.2 Task 2 — CLI single-shot due-source scheduler (DRY-RUN ONLY).

Computes this cycle's due-source plan and prints a readable summary of which
sources are due / skipped / running / unsupported / missing, plus which sources
*would* be started if this were applied.

This script is strictly read-only in Task 2:
- It only calls the read-only ``compute_due_sources()`` service.
- It does NOT create FetchRun rows.
- It does NOT schedule any background work or dispatch the fetch service.
- It does NOT trigger real fetches, LLM calls, summaries, or InsightCard generation.
- It does NOT write to the database.

``--apply`` is intentionally NOT implemented here. Real single-shot execution
(creating FetchRun rows) is Task 3.

Usage:
    python scripts/run_due_sources_once.py
    python scripts/run_due_sources_once.py --max-sources 3
    python scripts/run_due_sources_once.py --show-skipped
    python scripts/run_due_sources_once.py --show-running
    python scripts/run_due_sources_once.py --show-unsupported
    python scripts/run_due_sources_once.py --show-missing
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CLI single-shot due-source scheduler (dry-run only, Task 2)"
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


def _print_plan(plan, args: argparse.Namespace) -> None:
    print("[run_due_sources_once] DRY-RUN")
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

    print()
    print("No FetchRun created. This script is dry-run only in V1.0-beta.2 Task 2.")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    invalid = _validate_args(args)
    if invalid is not None:
        return invalid

    try:
        from app.db import SessionLocal
        from app.application.sources.due_sources import compute_due_sources
    except Exception as e:
        print(f"[ERROR] Failed to import required modules: {e}")
        return 1

    db = SessionLocal()
    try:
        plan = compute_due_sources(db, max_sources=args.max_sources)
        _print_plan(plan, args)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
