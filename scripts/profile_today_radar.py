#!/usr/bin/env python3
"""Profile RadarTodayService.build_today_view() performance.

Usage:
    python scripts/profile_today_radar.py
    python scripts/profile_today_radar.py --section all --page 1 --hours 24 --limit 50 --per-page 20
    python scripts/profile_today_radar.py --repeat 3
    python scripts/profile_today_radar.py --include-candidates
    python scripts/profile_today_radar.py --no-candidates
"""
from __future__ import annotations

import argparse
import sys
import time
from time import perf_counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class ProfileResult:
    scenario: str = ""
    total_ms: float = 0
    recent_items_query_ms: float = 0
    fallback_query_ms: float = 0
    sort_ms: float = 0
    full_display_map_ms: float = 0
    section_counts_ms: float = 0
    filter_and_pagination_ms: float = 0
    build_display_map_ms: float = 0
    build_today_card_map_ms: float = 0
    section_grouping_ms: float = 0
    selected_item_resolution_ms: float = 0
    panel_state_ms: float = 0
    fetch_run_summary_ms: float = 0
    quality_filter_stats_ms: float = 0
    compile_candidates_ms: float = 0
    template_context_total_ms: float = 0
    notes: list[str] = field(default_factory=list)

    def print_report(self) -> None:
        print(f"\n{'='*60}")
        print(f"Profile: {self.scenario}")
        print(f"{'='*60}")
        print(f"  Total time:                    {self.total_ms:.1f} ms")
        print(f"  Recent items query:            {self.recent_items_query_ms:.1f} ms")
        print(f"  Fallback query:               {self.fallback_query_ms:.1f} ms")
        print(f"  Sort items:                   {self.sort_ms:.1f} ms")
        print(f"  Full display map (all items): {self.full_display_map_ms:.1f} ms")
        print(f"  Section counts:                {self.section_counts_ms:.1f} ms")
        print(f"  Filter + pagination:           {self.filter_and_pagination_ms:.1f} ms")
        print(f"  Display map (page only):      {self.build_display_map_ms:.1f} ms")
        print(f"  Today card map:               {self.build_today_card_map_ms:.1f} ms")
        print(f"  Section grouping:              {self.section_grouping_ms:.1f} ms")
        print(f"  Selected item resolution:      {self.selected_item_resolution_ms:.1f} ms")
        print(f"  Panel state:                  {self.panel_state_ms:.1f} ms")
        print(f"  Fetch run summary:            {self.fetch_run_summary_ms:.1f} ms")
        print(f"  Quality filter stats:         {self.quality_filter_stats_ms:.1f} ms")
        print(f"  Compile candidates:            {self.compile_candidates_ms:.1f} ms")
        if self.notes:
            print(f"\n  Notes:")
            for note in self.notes:
                print(f"    - {note}")


def profile_build_today_view(
    db,
    section: str,
    page: int,
    hours: int,
    limit: int,
    per_page: int,
    include_candidates: bool,
) -> ProfileResult:
    """Profile a single call to RadarTodayService.build_today_view()."""
    from app.application.radar.today import RadarTodayService
    from app.application.candidates.compile_candidates import select_compile_candidates

    result = ProfileResult()
    result.scenario = (
        f"section={section} page={page} hours={hours} "
        f"limit={limit} per_page={per_page} "
        f"candidates={include_candidates}"
    )

    t0 = perf_counter()

    # ── Recent-window query ──────────────────────────────────────────
    from app.models import Source, SourceItem
    from sqlalchemy import func, or_, desc

    cutoff = datetime.utcnow() - timedelta(hours=hours)
    order = desc(func.coalesce(
        SourceItem.published_at,
        SourceItem.last_seen_at,
        SourceItem.first_seen_at,
    ))

    q0 = time.perf_counter()
    items = (
        db.query(SourceItem)
        .join(Source, Source.id == SourceItem.source_id)
        .filter(
            or_(
                SourceItem.first_seen_at >= cutoff,
                SourceItem.last_seen_at >= cutoff,
            ),
            Source.enabled.is_(True),
            SourceItem.url.isnot(None),
            SourceItem.url != "",
            SourceItem.title.isnot(None),
            SourceItem.title != "",
        )
        .order_by(order)
        .limit(limit)
        .all()
    )
    result.recent_items_query_ms = (time.perf_counter() - q0) * 1000

    # ── Fallback query ───────────────────────────────────────────────
    fallback_used = False
    q0 = time.perf_counter()
    if not items:
        fallback_used = True
        items = (
            db.query(SourceItem)
            .join(Source, Source.id == SourceItem.source_id)
            .filter(
                Source.enabled.is_(True),
                SourceItem.url.isnot(None),
                SourceItem.url != "",
                SourceItem.title.isnot(None),
                SourceItem.title != "",
            )
            .order_by(order)
            .limit(limit)
            .all()
        )
    result.fallback_query_ms = (time.perf_counter() - q0) * 1000

    # ── Sort ───────────────────────────────────────────────────────
    from app.application.radar.today import _radar_sort_key
    q0 = time.perf_counter()
    items = sorted(items, key=_radar_sort_key, reverse=True)
    result.sort_ms = (time.perf_counter() - q0) * 1000

    # ── Full display map (ALL items) ────────────────────────────────
    from app.application.candidates.display import build_candidate_display_card, CandidateDisplayCard
    q0 = time.perf_counter()
    full_display_map: dict[int, CandidateDisplayCard] = {
        item.id: build_candidate_display_card(item) for item in items
    }
    result.full_display_map_ms = (time.perf_counter() - q0) * 1000

    # ── Section counts ──────────────────────────────────────────────
    from app.application.radar.today import (
        SECTION_ORDER, TODAY_FOCUS_KEY, ALL_KEY, TODAY_FOCUS_SIZE,
        _categorize_item, RadarTodaySection, TodayItemCard,
    )
    q0 = time.perf_counter()
    section_counts: dict[str, int] = {key: 0 for key, _ in SECTION_ORDER}
    section_counts[TODAY_FOCUS_KEY] = min(len(items), TODAY_FOCUS_SIZE)
    for item in items[TODAY_FOCUS_SIZE:]:
        key = _categorize_item(item, full_display_map.get(item.id))
        section_counts[key] = section_counts.get(key, 0) + 1
    section_counts[ALL_KEY] = len(items)
    result.section_counts_ms = (time.perf_counter() - q0) * 1000

    # ── Filter + pagination ─────────────────────────────────────────
    q0 = time.perf_counter()
    if section == ALL_KEY:
        filtered_items = items
    elif section == TODAY_FOCUS_KEY:
        filtered_items = items[:TODAY_FOCUS_SIZE]
    else:
        filtered_items = [
            item for item in items[TODAY_FOCUS_SIZE:]
            if _categorize_item(item, full_display_map.get(item.id)) == section
        ]
    total_items_in_section = len(filtered_items)
    import math
    total_pages = max(1, math.ceil(total_items_in_section / per_page)) if total_items_in_section else 1
    page = min(page, total_pages)
    start = (page - 1) * per_page
    page_items = filtered_items[start:start + per_page]
    has_prev = page > 1
    has_next = page < total_pages
    result.filter_and_pagination_ms = (time.perf_counter() - q0) * 1000

    # ── Display map (page only) ───────────────────────────────────────
    q0 = time.perf_counter()
    display_map: dict[int, CandidateDisplayCard] = {
        item.id: full_display_map[item.id] for item in page_items
    }
    result.build_display_map_ms = (time.perf_counter() - q0) * 1000

    # ── Today card map ──────────────────────────────────────────────
    from app.application.radar.today import build_today_item_card
    q0 = time.perf_counter()
    today_card_map: dict[int, TodayItemCard] = {
        item.id: build_today_item_card(item, full_display_map.get(item.id))
        for item in page_items
    }
    result.build_today_card_map_ms = (time.perf_counter() - q0) * 1000

    # ── Section grouping ────────────────────────────────────────────
    q0 = time.perf_counter()
    full_buckets: dict[str, list] = {key: [] for key, _ in SECTION_ORDER}
    today_focus_ids = {i.id for i in items[:TODAY_FOCUS_SIZE]}
    for item in page_items:
        if item.id in today_focus_ids and section in (ALL_KEY, TODAY_FOCUS_KEY):
            full_buckets[TODAY_FOCUS_KEY].append(item)
        else:
            key = _categorize_item(item, full_display_map.get(item.id))
            full_buckets[key].append(item)
    sections = [
        RadarTodaySection(key=key, title=title, items=full_buckets[key])
        for key, title in SECTION_ORDER
    ]
    result.section_grouping_ms = (time.perf_counter() - q0) * 1000

    # ── Selected item resolution (stub — no item_id selected in profile) ──
    q0 = time.perf_counter()
    selected_item = None
    selected_missing = False
    result.selected_item_resolution_ms = (time.perf_counter() - q0) * 1000

    # ── Panel state ─────────────────────────────────────────────────
    from app.application.radar.today import _build_panel_state
    q0 = time.perf_counter()
    panel_state = _build_panel_state(db, selected_item)
    result.panel_state_ms = (time.perf_counter() - q0) * 1000

    # ── Fetch run summary ───────────────────────────────────────────
    q0 = time.perf_counter()
    service = RadarTodayService(db)
    fetch_run_summary = service.build_fetch_run_summary(None)
    result.fetch_run_summary_ms = (time.perf_counter() - q0) * 1000

    # ── Quality filter stats (only when section=all && page=1, matching production) ──
    q0 = time.perf_counter()
    quality_filter_stats = None
    if section == "all" and page == 1:
        quality_filter_stats = service.compute_quality_filter_stats(hours)
    result.quality_filter_stats_ms = (time.perf_counter() - q0) * 1000

    # ── Compile candidates ───────────────────────────────────────────
    q0 = time.perf_counter()
    compile_candidates = []
    if include_candidates and section == ALL_KEY and page == 1:
        compile_candidates = select_compile_candidates(
            db,
            hours=hours,
            limit=10,
            per_source_limit=3,
            max_scan=300,
        )
    result.compile_candidates_ms = (time.perf_counter() - q0) * 1000

    t1 = perf_counter()
    result.total_ms = (t1 - t0) * 1000

    # ── Notes ───────────────────────────────────────────────────────
    result.notes.append(f"Items in window: {len(items)}")
    result.notes.append(f"Page items: {len(page_items)}")
    result.notes.append(f"Fallback used: {fallback_used}")
    if compile_candidates:
        result.notes.append(f"Compile candidates returned: {len(compile_candidates)}")

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile RadarTodayService.build_today_view()")
    parser.add_argument("--section", default="all")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--per-page", type=int, default=20)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--include-candidates", action="store_true", default=True)
    parser.add_argument("--no-candidates", action="store_true")
    args = parser.parse_args()

    include_candidates = args.include_candidates and not args.no_candidates

    print(f"Loading database...")
    from app.db import SessionLocal as _SL
    db = _SL()

    try:
        print(f"\nProfiling RadarTodayService.build_today_view()")
        print(f"  section={args.section} page={args.page} hours={args.hours}")
        print(f"  limit={args.limit} per_page={args.per_page}")
        print(f"  include_candidates={include_candidates}")
        print(f"  repeat={args.repeat}x\n")

        results: list[ProfileResult] = []
        for i in range(args.repeat):
            result = profile_build_today_view(
                db,
                section=args.section,
                page=args.page,
                hours=args.hours,
                limit=args.limit,
                per_page=args.per_page,
                include_candidates=include_candidates,
            )
            results.append(result)
            if args.repeat > 1:
                print(f"  Run {i+1}/{args.repeat}: {result.total_ms:.1f} ms total")

        if args.repeat > 1:
            avg = ProfileResult()
            avg.scenario = f"AVG({args.repeat} runs)"
            avg.total_ms = sum(r.total_ms for r in results) / len(results)
            avg.recent_items_query_ms = sum(r.recent_items_query_ms for r in results) / len(results)
            avg.fallback_query_ms = sum(r.fallback_query_ms for r in results) / len(results)
            avg.sort_ms = sum(r.sort_ms for r in results) / len(results)
            avg.full_display_map_ms = sum(r.full_display_map_ms for r in results) / len(results)
            avg.section_counts_ms = sum(r.section_counts_ms for r in results) / len(results)
            avg.filter_and_pagination_ms = sum(r.filter_and_pagination_ms for r in results) / len(results)
            avg.build_display_map_ms = sum(r.build_display_map_ms for r in results) / len(results)
            avg.build_today_card_map_ms = sum(r.build_today_card_map_ms for r in results) / len(results)
            avg.section_grouping_ms = sum(r.section_grouping_ms for r in results) / len(results)
            avg.selected_item_resolution_ms = sum(r.selected_item_resolution_ms for r in results) / len(results)
            avg.panel_state_ms = sum(r.panel_state_ms for r in results) / len(results)
            avg.fetch_run_summary_ms = sum(r.fetch_run_summary_ms for r in results) / len(results)
            avg.quality_filter_stats_ms = sum(r.quality_filter_stats_ms for r in results) / len(results)
            avg.compile_candidates_ms = sum(r.compile_candidates_ms for r in results) / len(results)
            results[-1].notes = results[0].notes
            results[-1].print_report()
        else:
            results[0].print_report()

        # Highlight most expensive stages
        if results:
            r = results[-1]
            stages = [
                ("recent_items_query", r.recent_items_query_ms),
                ("fallback_query", r.fallback_query_ms),
                ("sort", r.sort_ms),
                ("full_display_map", r.full_display_map_ms),
                ("section_counts", r.section_counts_ms),
                ("filter_and_pagination", r.filter_and_pagination_ms),
                ("display_map", r.build_display_map_ms),
                ("today_card_map", r.build_today_card_map_ms),
                ("section_grouping", r.section_grouping_ms),
                ("selected_item_resolution", r.selected_item_resolution_ms),
                ("panel_state", r.panel_state_ms),
                ("fetch_run_summary", r.fetch_run_summary_ms),
                ("quality_filter_stats", r.quality_filter_stats_ms),
                ("compile_candidates", r.compile_candidates_ms),
            ]
            stages.sort(key=lambda x: -x[1])
            print(f"\n  Top 3 most expensive stages:")
            for name, ms in stages[:3]:
                pct = 100 * ms / r.total_ms if r.total_ms > 0 else 0
                print(f"    {name}: {ms:.1f} ms ({pct:.1f}%)")

    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
