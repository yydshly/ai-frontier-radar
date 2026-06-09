#!/usr/bin/env python3
"""Diagnostic: check SourceItem raw_metadata_json for Chinese summary fields.

Reads zh_one_liner / zh_summary coverage in recent SourceItems.
Read-only — no DB writes, no LLM calls, no SourceItem modifications.

Usage:
    python scripts/check_radar_summary_fields.py
    python scripts/check_radar_summary_fields.py --limit 20
    python scripts/check_radar_summary_fields.py --source-key openai_news --limit 20
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal
from app.models import SourceItem


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Check SourceItem Chinese summary field coverage — read-only."
    )
    parser.add_argument(
        "--source-key",
        type=str,
        default=None,
        help="Filter to a specific source_key.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of recent items to check (default: 20).",
    )
    return parser


def _check_fields(raw_json: str) -> tuple[bool, bool, list[str]]:
    """Return (has_zh_one_liner, has_zh_summary, fallback_fields)."""
    try:
        meta = json.loads(raw_json) if raw_json else {}
    except Exception:
        meta = {}
    has_zh_ol = bool(meta.get("zh_one_liner"))
    has_zh_sum = bool(meta.get("zh_summary"))
    fallbacks = []
    if not has_zh_ol and not has_zh_sum:
        if meta.get("rss_summary"):
            fallbacks.append("rss_summary")
        if meta.get("description"):
            fallbacks.append("description")
        if meta.get("detail_description"):
            fallbacks.append("detail_description")
    return has_zh_ol, has_zh_sum, fallbacks


def _run(args):
    db = SessionLocal()
    try:
        query = db.query(SourceItem).order_by(SourceItem.id.desc())
        if args.source_key:
            query = query.filter(SourceItem.source_key == args.source_key)
        items = query.limit(args.limit).all()

        print(f"\n# Radar summary field diagnostic (limit={args.limit}" +
              (f", source_key={args.source_key}" if args.source_key else "") + ")\n")

        total = len(items)
        zh_ol_count = 0
        zh_sum_count = 0

        for item in items:
            has_zh_ol, has_zh_sum, fallbacks = _check_fields(item.raw_metadata_json or "")
            if has_zh_ol:
                zh_ol_count += 1
            if has_zh_sum:
                zh_sum_count += 1

            fallback_str = ", fallback: " + ", ".join(fallbacks) if fallbacks else ""

            print(f"  # {item.id}  [{item.source_key}]")
            title = (item.title or "").replace("\n", " ")[:60]
            print(f"    title : {title}")
            print(f"    has_zh_one_liner : {has_zh_ol}")
            print(f"    has_zh_summary    : {has_zh_sum}" + fallback_str)

        print(f"\n---\nCoverage: {zh_ol_count}/{total} have zh_one_liner, "
              f"{zh_sum_count}/{total} have zh_summary")

        if zh_ol_count == 0 and zh_sum_count == 0:
            print("\nConclusion: ALL items fall back to English metadata fields.")
            print("Page displaying English is NORMAL — no zh_one_liner/zh_summary in DB.")
            print("Run: python scripts/generate_one_liners.py to populate these fields.")
        else:
            print("\nConclusion: Some items have Chinese fields — if page still shows")
            print("English, the display card / summary extraction logic may have a bug.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = _build_arg_parser()
    args = parser.parse_args()
    _run(args)
