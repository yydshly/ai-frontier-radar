#!/usr/bin/env python3
"""Sync source configurations from sources.example.yaml to the database.

Usage:
    python scripts/sync_sources_from_config.py          # dry-run (default)
    python scripts/sync_sources_from_config.py --apply   # actually sync
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import SessionLocal, init_db
from app.sources.db_sync import sync_sources_config_to_db


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync sources from YAML config to DB")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes to DB. Without this flag, runs dry-run.",
    )
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        print("Loading config from sources.example.yaml...")
        dry_run = not args.apply
        stats = sync_sources_config_to_db(db, force_reload=True, dry_run=dry_run)
        print(f"\nConfig loaded: {stats['total']} sources")
        print(f"  Would create: {stats['created']}")
        print(f"  Would update: {stats['updated']}")
        print(f"  Would disable: {stats['disabled']}")

        if dry_run:
            print("\n[DRY-RUN] Pass --apply to write changes to DB.")
            return 0

        print("\n[APPLY] Writing changes to DB...")
        print(f"Done. created={stats['created']}, updated={stats['updated']}, disabled={stats['disabled']}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
