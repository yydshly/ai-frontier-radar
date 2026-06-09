#!/usr/bin/env python3
"""Generate Chinese one-liner summaries for candidate SourceItems."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.application.candidates.one_liner import (  # noqa: E402
    CandidateOneLinerService,
    get_one_liner_settings,
)
from app.db import SessionLocal  # noqa: E402
from app.models import SourceItem  # noqa: E402


SCRIPT_ELIGIBLE_STATUSES = ("discovered", "failed", "manual_required")


def select_items(db, source_key: str | None, limit: int) -> list[SourceItem]:
    query = (
        db.query(SourceItem)
        .filter(SourceItem.status.in_(SCRIPT_ELIGIBLE_STATUSES))
        .order_by(SourceItem.last_seen_at.desc(), SourceItem.id.desc())
    )
    if source_key:
        query = query.filter(SourceItem.source_key == source_key)

    selected: list[SourceItem] = []
    for item in query.limit(limit * 3).all():
        raw = item.raw_metadata_json or ""
        if '"zh_one_liner"' in raw:
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate candidate Chinese one-liners.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--source-key", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    limit = max(1, args.limit)
    settings = get_one_liner_settings()
    db = SessionLocal()
    try:
        items = select_items(db, args.source_key, limit)
        print(f"selected={len(items)} limit={limit} dry_run={args.dry_run}")
        print(f"enabled={settings.enabled} provider={settings.provider}")

        if args.dry_run:
            for item in items:
                print(f"DRY item_id={item.id} source={item.source_key} title={(item.title or '')[:80]}")
            return 0

        if not settings.enabled:
            print("ONE_LINER_ENABLED=false; no one-liner generation will run.")
            print(
                "Set ONE_LINER_ENABLED=true and ONE_LINER_PROVIDER=llm_profile "
                "to use the configured LLM profile."
            )
            return 0

        service = CandidateOneLinerService(db, settings=settings)
        results = service.generate_for_items(items, limit=limit)
        success = sum(1 for r in results if r.status == "success")
        skipped = sum(1 for r in results if r.status == "skipped")
        failed = sum(1 for r in results if r.status == "failed")
        for result in results:
            print(
                f"item_id={result.item_id} status={result.status} "
                f"model={result.model or '-'} error={result.error or '-'}"
            )
        print(f"done success={success} skipped={skipped} failed={failed}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
