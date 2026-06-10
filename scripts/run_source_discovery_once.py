#!/usr/bin/env python3
"""Run one controlled YAML source discovery cycle.

Default mode is dry-run and read-only. Apply mode is explicit and disables
fetch-run auto summaries so this script does not call LLMs.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run source discovery once")
    parser.add_argument(
        "--mode",
        choices=["bootstrap", "daily_increment"],
        required=True,
        help="bootstrap initializes recent YAML source content; daily_increment uses due-source logic.",
    )
    parser.add_argument(
        "--max-items-per-source",
        type=int,
        default=20,
        help="Per-source fetch limit. Values are capped at 50.",
    )
    parser.add_argument(
        "--max-sources",
        type=int,
        default=15,
        help="Maximum sources to consider for this run.",
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true", help="Plan only; no writes and no enqueue.")
    action.add_argument("--apply", action="store_true", help="Execute discovery with explicit apply gate.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        from app.db import SessionLocal
        from app.application.sources.discovery_runs import (
            SourceDiscoveryRunSettings,
            run_source_discovery,
        )
    except Exception as exc:
        print(f"[ERROR] import failed: {exc}")
        return 1

    db = SessionLocal()
    try:
        result = run_source_discovery(
            db,
            SourceDiscoveryRunSettings(
                mode=args.mode,
                max_items_per_source=args.max_items_per_source,
                max_sources=args.max_sources,
                dry_run=not args.apply,
            ),
        )
    finally:
        db.close()

    print("source_discovery_result:")
    print(f"  mode: {result.mode}")
    print(f"  dry_run: {str(result.dry_run).lower()}")
    print(f"  total_sources: {result.total_sources}")
    print(f"  eligible_sources: {result.eligible_sources}")
    print(f"  started: {result.started}")
    print(f"  skipped: {result.skipped}")
    print(f"  unsupported: {result.unsupported}")
    print(f"  failed: {result.failed}")
    print(f"  message: {result.message}")
    print("  source_results:")
    if not result.source_results:
        print("    []")
    else:
        for item in result.source_results:
            run_part = f" run_id={item.run_id}" if item.run_id is not None else ""
            print(f"    - {item.source_key}: {item.status}{run_part} {item.message}".rstrip())

    if result.dry_run:
        print()
        print("No SourceItem or FetchRun rows were written. Re-run with --apply to execute.")
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
