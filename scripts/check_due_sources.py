#!/usr/bin/env python3
"""
Read-only diagnostic script for due-source computation.

Does NOT:
- Trigger any fetches
- Write to the database
- Call LLM services
- Access the network

Usage:
    python scripts/check_due_sources.py
    python scripts/check_due_sources.py --max-sources 10
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


def _format_decision(d: object) -> str:
    parts = [
        f"  - {getattr(d, 'source_key', '?')}",
        f"    reason={getattr(d, 'reason', '?')}",
    ]
    for attr in (
        "latest_run_status",
        "latest_run_started_at",
        "next_due_at",
        "fetch_interval_hours",
    ):
        val = getattr(d, attr, None)
        if val is not None:
            if isinstance(val, datetime):
                val = _format_dt(val)
            parts.append(f"    {attr}={val}")
    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Due-source diagnostic (read-only)")
    parser.add_argument(
        "--max-sources",
        type=int,
        default=None,
        metavar="N",
        help="Cap on number of due sources shown (excess moved to skipped)",
    )
    args = parser.parse_args()

    print("Due source check")
    print(f"max_sources: {args.max_sources}")
    print()

    try:
        from app.db import SessionLocal
        from app.application.sources.due_sources import compute_due_sources
    except Exception as e:
        print(f"[ERROR] Failed to import required modules: {e}")
        sys.exit(1)

    db = SessionLocal()
    try:
        plan = compute_due_sources(db, now=datetime.utcnow(), max_sources=args.max_sources)
    except Exception as e:
        print(f"[ERROR] Failed to compute due sources: {e}")
        sys.exit(1)
    finally:
        db.close()

    print(f"generated_at: {_format_dt(plan.generated_at)}")
    print(f"total_configured: {plan.total_configured}")
    print(f"due: {plan.due_count}")
    print(f"skipped: {plan.skipped_count}")
    print(f"running: {plan.running_count}")
    print(f"unsupported: {plan.unsupported_count}")
    print(f"missing: {plan.missing_count}")
    print()

    if plan.due:
        print("Due:")
        for d in plan.due:
            print(_format_decision(d))
        print()

    if plan.skipped:
        print("Skipped:")
        for d in plan.skipped:
            print(_format_decision(d))
        print()

    if plan.running:
        print("Running:")
        for d in plan.running:
            print(_format_decision(d))
        print()

    if plan.unsupported:
        print("Unsupported:")
        for d in plan.unsupported:
            print(_format_decision(d))
        print()

    if plan.missing:
        print("Missing:")
        for d in plan.missing:
            print(_format_decision(d))
        print()

    sys.exit(0)


if __name__ == "__main__":
    main()
