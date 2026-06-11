#!/usr/bin/env python3
"""Single-source probe script for V1.0-beta.15 Phase 4.2.

Probes a specific source to produce clean SourceItems for today radar.

Usage:
    python scripts/run_source_probe.py --source openai_news
    python scripts/run_source_probe.py --source huggingface_blog
    python scripts/run_source_probe.py --source arxiv_cs_ai
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe a single source to produce SourceItems."
    )
    parser.add_argument(
        "--source",
        type=str, required=True,
        help="source_key to probe (e.g. openai_news, huggingface_blog, arxiv_cs_ai).",
    )
    parser.add_argument(
        "--timeout",
        type=int, default=20,
        help="HTTP timeout in seconds (default: 20).",
    )
    args = parser.parse_args()

    print(f"[PROBE] Initializing database...")
    try:
        from app.db import SessionLocal, init_db
        from app.models import Source
        from app.sources.rss_probe import run_rss_probe_for_source
        from app.sources.html_index_probe import run_html_index_probe_for_source
    except Exception as e:
        print(f"[ERROR] Failed to import app modules: {e}")
        return 1

    init_db()
    db = SessionLocal()

    try:
        # Find source
        source = db.query(Source).filter(Source.source_key == args.source).first()
        if source is None:
            print(f"[ERROR] Source '{args.source}' not found in database.")
            return 1

        print(f"[PROBE] Found source: {source.name} (key={source.source_key})")
        print(f"[PROBE]   strategy: {source.fetch_strategy}")
        print(f"[PROBE]   enabled:  {source.enabled}")

        if not source.enabled:
            print(f"[WARN] Source is disabled. Skipping probe.")
            return 0

        strategy = source.fetch_strategy
        if strategy == "rss":
            print(f"[PROBE] Running RSS probe...")
            fetch_run = run_rss_probe_for_source(
                db, source, timeout_seconds=args.timeout
            )
            print(f"[PROBE] FetchRun id={fetch_run.id} status={fetch_run.status}")
            print(f"[PROBE]   items_found:   {fetch_run.items_found}")
            print(f"[PROBE]   items_new:     {fetch_run.items_new}")
            print(f"[PROBE]   items_updated: {fetch_run.items_updated}")
            print(f"[PROBE]   items_failed:  {fetch_run.items_failed}")
            if fetch_run.error_message:
                print(f"[PROBE]   error: {fetch_run.error_message}")

        elif strategy == "html_index":
            print(f"[PROBE] Running HTML index probe...")
            fetch_run = run_html_index_probe_for_source(
                db, source, timeout_seconds=args.timeout
            )
            print(f"[PROBE] FetchRun id={fetch_run.id} status={fetch_run.status}")
            print(f"[PROBE]   items_found:   {fetch_run.items_found}")
            print(f"[PROBE]   items_new:     {fetch_run.items_new}")
            print(f"[PROBE]   items_updated: {fetch_run.items_updated}")
            print(f"[PROBE]   items_failed:  {fetch_run.items_failed}")
            if fetch_run.error_message:
                print(f"[PROBE]   error: {fetch_run.error_message}")

        elif strategy == "manual":
            print(f"[PROBE] Manual source — no automatic probe available.")
            return 0

        else:
            print(f"[ERROR] Unknown fetch_strategy: {strategy}")
            return 1

        print(f"[PROBE] Done.")
        return 0

    except Exception as e:
        db.rollback()
        print(f"[ERROR] Probe failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
