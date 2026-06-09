#!/usr/bin/env python
"""Read-only Source table health diagnostic.

Run with:
    python scripts/check_sources_health.py

No arguments, no database mutations.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import SessionLocal
from app.models import Source
from app.application.sources.fetch_service import SUPPORTED_STRATEGIES
from app.sources.config_loader import list_sources


def main():
    db = SessionLocal()
    try:
        sources = (
            db.query(Source)
            .order_by(Source.source_key.asc(), Source.id.asc())
            .all()
        )

        enabled = [s for s in sources if s.enabled]
        supported_enabled = [
            s for s in enabled if s.fetch_strategy in SUPPORTED_STRATEGIES
        ]
        unsupported_enabled = [
            s for s in enabled if s.fetch_strategy not in SUPPORTED_STRATEGIES
        ]

        # Count unique source_keys
        key_counts = Counter(s.source_key for s in sources)
        duplicate_keys = {k: c for k, c in key_counts.items() if c > 1}
        unique_count = sum(1 for c in key_counts.values() if c == 1)
        total_duplicate_rows = sum(c - 1 for c in key_counts.values() if c > 1)

        print("Source health check")
        print(f"total_sources: {len(sources)}")
        print(f"enabled_sources: {len(enabled)}")
        print(f"supported_enabled_sources: {len(supported_enabled)}")
        print(f"unique_source_keys: {len(key_counts)}")
        print(f"duplicate_source_keys: {len(duplicate_keys)}")
        print(f"unsupported_enabled_sources: {len(unsupported_enabled)}")

        if duplicate_keys:
            print()
            print("Duplicate source_key:")
            for key, count in sorted(duplicate_keys.items(), key=lambda x: -x[1])[:20]:
                print(f"  - {key}: {count} rows")

        print()
        if duplicate_keys:
            total_dup = sum(c - 1 for c in key_counts.values() if c > 1)
            print(f"Recommendation:")
            print(f"  Source table has {len(duplicate_keys)} duplicate source_key(s) "
                  f"({total_dup} extra rows).")
            print(f"  Batch update will dedupe by source_key automatically.")
        else:
            print("Source table is healthy — no duplicate source_key rows found.")

        # Config vs DB comparison — "configured" here means "configured as radar sources"
        configured = list_sources()
        configured_all_keys = {s.source_key for s in configured}
        configured_enabled_keys = {s.source_key for s in configured if s.enabled}

        db_enabled_keys = {s.source_key for s in enabled}
        enabled_not_in_config = db_enabled_keys - configured_enabled_keys
        configured_missing_in_db = configured_enabled_keys - db_enabled_keys

        print()
        print("Configured radar sources vs DB comparison:")
        print(f"configured_sources: {len(configured_all_keys)}")
        print(f"configured_enabled_sources: {len(configured_enabled_keys)}")
        print(f"db_enabled_unique_sources: {len(db_enabled_keys)}")
        print(f"enabled_not_in_config: {len(enabled_not_in_config)}")
        print(f"configured_missing_in_db: {len(configured_missing_in_db)}")

        if enabled_not_in_config:
            print()
            print("Enabled sources not in configured radar sources:")
            for key in sorted(enabled_not_in_config)[:20]:
                print(f"  - {key}")

        if configured_missing_in_db:
            print()
            print("Configured radar sources missing in DB:")
            for key in sorted(configured_missing_in_db)[:20]:
                print(f"  - {key}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
