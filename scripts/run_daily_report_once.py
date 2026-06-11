#!/usr/bin/env python3
"""
CLI for today's core report generation (P-003-2 / Phase D).

DRY-RUN by default — assembles the compile input (today's Chinese one-liners)
and prints it WITHOUT calling any LLM.

``--apply`` additionally requires ``DAILY_REPORT_ENABLED=true`` in the
environment; otherwise it exits without calling the LLM. A single LLM call is
made per generation, capped by ``DAILY_REPORT_MAX_ITEMS``.

Usage:
    python scripts/run_daily_report_once.py
    DAILY_REPORT_ENABLED=true python scripts/run_daily_report_once.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _configure_stdio_encoding() -> None:
    """Force UTF-8 output encoding on Windows to prevent UnicodeEncodeError."""
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Today's core report generation (dry-run by default)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Call the LLM to generate. Requires DAILY_REPORT_ENABLED=true.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _configure_stdio_encoding()
    args = parse_args(argv)

    # Gate: --apply requires the explicit enable flag, checked before any LLM.
    if args.apply and os.getenv("DAILY_REPORT_ENABLED", "").strip().lower() != "true":
        print("[ERROR] --apply requires DAILY_REPORT_ENABLED=true.")
        return 2

    try:
        from app.db import SessionLocal
        from app.application.radar.daily_report import (
            generate_daily_report,
            build_daily_report_input,
        )
    except Exception as e:
        print(f"[ERROR] Failed to import required modules: {e}")
        return 1

    db = SessionLocal()
    try:
        print("[run_daily_report_once]", "APPLY" if args.apply else "DRY-RUN")
        result = generate_daily_report(db, apply=args.apply)
        print(f"date={result.date_label}")
        print(f"input_items={result.input_item_count}")
        print(f"status={result.status}")
        print(f"message={result.message}")

        if result.status == "dry_run":
            payload = build_daily_report_input(db)
            print()
            print("compile_input_preview:")
            if payload.bullet_sources:
                for b in payload.bullet_sources:
                    print(f"  - {b[:80]}")
            else:
                print("  (none)")
            print()
            print("No LLM was called. Use --apply with DAILY_REPORT_ENABLED=true to generate.")
        elif result.status == "generated":
            print()
            print(f"title: {result.title}")
            print(f"overview: {result.overview}")
            print("highlights:")
            for h in result.highlights:
                print(f"  - {h}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
