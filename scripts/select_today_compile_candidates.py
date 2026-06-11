#!/usr/bin/env python3
"""Select today compile candidates for InsightCard generation — V1.0-beta.16 Phase 4.3.

Default dry-run (read-only). Outputs ranked candidates without writing anything.

Usage:
    python scripts/select_today_compile_candidates.py                          # dry-run
    python scripts/select_today_compile_candidates.py --hours 24 --limit 10  # custom
    python scripts/select_today_compile_candidates.py --per-source-limit 3    # per-source cap
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Reuse CompileCandidate and select_compile_candidates from app layer
from app.application.candidates.compile_candidates import (
    CompileCandidate,
    select_compile_candidates,
)

# Alias for backward compatibility with existing output format
ScoredCandidate = CompileCandidate


# ── Output formatting ────────────────────────────────────────────────────────────


def format_candidates(candidates: list[ScoredCandidate]) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("Today Compile Candidate Selection (V1.0-beta.16 Phase 4.3)")
    lines.append("=" * 70)
    lines.append(f"  selected_candidates: {len(candidates)}")
    lines.append("")

    if not candidates:
        lines.append("  (no candidates found)")
    else:
        for c in candidates:
            lines.append(f"[{c.rank}] id={c.source_item_id} source_key={c.source_key} score={c.score}")
            lines.append(f"    compile_basis={c.compile_basis} "
                         f"reasons={', '.join(c.reasons) if c.reasons else 'none'}")
            lines.append(f"    title: {c.title[:60]}")
            lines.append(f"    url:   {c.url[:70]}")
            lines.append(f"    first_seen: {c.first_seen_at[:16] if c.first_seen_at else '?'}")
    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Select top compile candidates from today radar (dry-run)."
    )
    parser.add_argument(
        "--hours", type=int, default=24,
        help="Time window in hours (default: 24).",
    )
    parser.add_argument(
        "--limit", type=int, default=10,
        help="Maximum candidates to return (default: 10).",
    )
    parser.add_argument(
        "--per-source-limit", type=int, default=3,
        help="Max candidates per source (default: 3).",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output as JSON instead of human-readable.",
    )
    args = parser.parse_args()

    print("Loading database...")
    try:
        from app.db import SessionLocal, init_db
    except Exception as e:
        print(f"[ERROR] Failed to import app modules: {e}")
        return 1

    init_db()
    db = SessionLocal()

    try:
        candidates = select_compile_candidates(
            db,
            hours=args.hours,
            limit=args.limit,
            per_source_limit=args.per_source_limit,
        )

        if args.json:
            output = [
                {
                    "rank": c.rank,
                    "source_item_id": c.source_item_id,
                    "source_key": c.source_key,
                    "title": c.title,
                    "url": c.url,
                    "score": c.score,
                    "reasons": c.reasons,
                    "compile_basis": c.compile_basis,
                    "published_at": c.published_at,
                    "first_seen_at": c.first_seen_at,
                }
                for c in candidates
            ]
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            print(format_candidates(candidates))

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
