#!/usr/bin/env python3
"""Audit today radar dataset quality — V1.0-beta.16.

Read-only audit of SourceItem dataset to understand:
- Total items and distribution by source
- How many items have titles, URLs, summaries, snapshots, InsightCards
- Whether newly probed items are actually new vs historical
- What percentage of items are eligible for InsightCard generation

Usage:
    python scripts/audit_today_radar_dataset.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def analyze_dataset(db) -> dict:
    """Analyze the SourceItem dataset. Returns a dict of stats."""
    from app.models import SourceItem, Source, InsightCard
    from app.application.content.content_snapshot import get_snapshot_path

    now = datetime.utcnow()
    cutoff_24h = now - timedelta(hours=24)
    cutoff_48h = now - timedelta(hours=48)

    all_items = db.query(SourceItem).all()
    total = len(all_items)

    # By source
    by_source: dict[str, dict] = defaultdict(lambda: {
        "total": 0, "new_24h": 0, "new_48h": 0,
        "with_title": 0, "with_url": 0,
        "with_zh_one_liner": 0, "with_zh_summary": 0,
        "with_metadata_summary": 0, "missing_all_summary": 0,
        "with_summary": 0, "with_snapshot": 0, "with_card": 0,
        "discovered": 0, "compiled": 0, "fetched": 0, "other_status": 0,
    })

    for item in all_items:
        s = item.source_key
        by_source[s]["total"] += 1

        # Time filters
        fs = item.first_seen_at
        if fs and fs >= cutoff_24h:
            by_source[s]["new_24h"] += 1
        if fs and fs >= cutoff_48h:
            by_source[s]["new_48h"] += 1

        # Content completeness
        if item.title and item.title.strip():
            by_source[s]["with_title"] += 1
        if item.url and item.url.strip():
            by_source[s]["with_url"] += 1

        # Parse raw_metadata
        raw = item.raw_metadata_json
        has_zh_one_liner = False
        has_zh_summary = False
        has_metadata_summary = False  # English source summary
        if raw:
            try:
                meta = json.loads(raw)
                has_zh_one_liner = bool(meta.get("zh_one_liner") and str(meta.get("zh_one_liner")).strip())
                has_zh_summary = bool(meta.get("zh_summary") and str(meta.get("zh_summary")).strip())
                # English source summary: any of the L0 fields that are non-empty and not Chinese
                _src_keys = ("detail_description", "summary", "description", "excerpt",
                             "content_snippet", "og_description", "meta_description",
                             "rss_summary", "rss_description")
                has_metadata_summary = any(
                    meta.get(k) and len(str(meta.get(k)).strip()) >= 30
                    for k in _src_keys
                )
                summary_status = meta.get("summary_status")
                summary_basis = meta.get("summary_basis")
                insight_status = meta.get("insight_status")
            except Exception:
                summary_status = None
                summary_basis = None
                insight_status = None
        else:
            summary_status = None
            summary_basis = None
            insight_status = None

        if has_zh_one_liner:
            by_source[s]["with_zh_one_liner"] += 1
        if has_zh_summary:
            by_source[s]["with_zh_summary"] += 1
        if has_metadata_summary:
            by_source[s]["with_metadata_summary"] += 1
        if not has_zh_one_liner and not has_zh_summary and not has_metadata_summary:
            by_source[s]["missing_all_summary"] += 1

        has_summary = has_zh_one_liner or has_zh_summary or has_metadata_summary
        if has_summary:
            by_source[s]["with_summary"] += 1

        # Snapshot
        if get_snapshot_path(item.id).exists():
            by_source[s]["with_snapshot"] += 1

        # Card
        if item.insight_card_id:
            by_source[s]["with_card"] += 1

        # Status breakdown
        status = item.status
        if status == "discovered":
            by_source[s]["discovered"] += 1
        elif status in ("compiled", "fetched"):
            by_source[s]["compiled" if status == "compiled" else "fetched"] += 1
        else:
            by_source[s]["other_status"] += 1

    # Overall stats
    # Compute per-item summary stats for overall counts
    overall_zh_one_liner = 0
    overall_zh_summary = 0
    overall_metadata_summary = 0
    overall_missing_all = 0
    _src_keys = ("detail_description", "summary", "description", "excerpt",
                 "content_snippet", "og_description", "meta_description",
                 "rss_summary", "rss_description")
    for i in all_items:
        raw = i.raw_metadata_json
        h_zh_ol = False
        h_zh_sum = False
        h_meta = False
        if raw:
            try:
                meta = json.loads(raw)
                h_zh_ol = bool(meta.get("zh_one_liner") and str(meta.get("zh_one_liner")).strip())
                h_zh_sum = bool(meta.get("zh_summary") and str(meta.get("zh_summary")).strip())
                h_meta = any(
                    meta.get(k) and len(str(meta.get(k)).strip()) >= 30
                    for k in _src_keys
                )
            except Exception:
                pass
        if h_zh_ol:
            overall_zh_one_liner += 1
        if h_zh_sum:
            overall_zh_summary += 1
        if h_meta:
            overall_metadata_summary += 1
        if not h_zh_ol and not h_zh_sum and not h_meta:
            overall_missing_all += 1

    stats = {
        "total_source_items": total,
        "new_items_last_24h": sum(1 for i in all_items if i.first_seen_at and i.first_seen_at >= cutoff_24h),
        "new_items_last_48h": sum(1 for i in all_items if i.first_seen_at and i.first_seen_at >= cutoff_48h),
        "with_title": sum(1 for i in all_items if i.title and i.title.strip()),
        "with_url": sum(1 for i in all_items if i.url and i.url.strip()),
        "with_zh_one_liner": overall_zh_one_liner,
        "with_zh_summary": overall_zh_summary,
        "with_metadata_summary": overall_metadata_summary,
        "missing_all_summary": overall_missing_all,
        "with_summary": overall_zh_one_liner + overall_zh_summary + overall_metadata_summary,
        "with_snapshot": sum(1 for i in all_items if get_snapshot_path(i.id).exists()),
        "with_insight_card": sum(1 for i in all_items if i.insight_card_id),
        "status_discovered": sum(1 for i in all_items if i.status == "discovered"),
        "status_fetched": sum(1 for i in all_items if i.status == "fetched"),
        "status_compiled": sum(1 for i in all_items if i.status == "compiled"),
        "by_source": dict(by_source),
    }

    # Top sources by new items (24h)
    stats["top_sources_by_new_items_24h"] = sorted(
        [(s, d["new_24h"]) for s, d in by_source.items()],
        key=lambda x: -x[1]
    )[:10]

    # Eligibility for InsightCard generation (V1.0-beta.16 Phase 4.3)
    # Three categories:
    # - already_compiled: compiled status OR has insight_card_id
    # - metadata_compile_candidates: discovered, no card, has rich RSS/metadata text in raw_metadata_json
    # - fulltext_compile_candidates: discovered, no card, has snapshot file (URL fetch fallback)
    already_compiled = 0
    metadata_compile = 0
    fulltext_compile = 0

    SNAPSHOT_MIN_CHARS = 120  # matches insight_compiler.SNAPSHOT_MIN_CHARS

    for item in all_items:
        # Already compiled or has card
        if item.status == "compiled" or item.insight_card_id:
            already_compiled += 1
            continue

        # Only categorize discovered items without cards
        if item.status != "discovered":
            continue

        # Check for snapshot file
        has_snapshot = get_snapshot_path(item.id).exists()
        if has_snapshot:
            fulltext_compile += 1
            continue

        # Check for rich metadata text (RSS summary, description, etc.)
        raw = item.raw_metadata_json
        if raw:
            try:
                meta = json.loads(raw)
                # Check any of the known metadata summary fields
                for field in ("zh_summary", "summary_zh", "zh_one_liner",
                               "summary", "rss_summary", "description",
                              "detail_description", "content_snippet"):
                    if meta.get(field) and len(str(meta[field])) >= SNAPSHOT_MIN_CHARS:
                        metadata_compile += 1
                        break
            except Exception:
                pass

    stats["already_compiled_items"] = already_compiled
    stats["metadata_compile_candidates"] = metadata_compile
    stats["fulltext_compile_candidates"] = fulltext_compile

    # Time range
    first_seen_times = [i.first_seen_at for i in all_items if i.first_seen_at]
    if first_seen_times:
        stats["oldest_first_seen_at"] = min(first_seen_times).isoformat()
        stats["newest_first_seen_at"] = max(first_seen_times).isoformat()

    return stats


def _has_summary(raw: str | None) -> bool:
    if not raw:
        return False
    try:
        meta = json.loads(raw)
        return bool(meta.get("zh_summary") or meta.get("summary_zh"))
    except Exception:
        return False


def format_report(stats: dict) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("Today Radar Dataset Quality Audit (V1.0-beta.16)")
    lines.append("=" * 70)
    lines.append("")

    lines.append("## Overall Stats")
    lines.append(f"  total_source_items:      {stats['total_source_items']}")
    lines.append(f"  new_items_last_24h:     {stats['new_items_last_24h']}")
    lines.append(f"  new_items_last_48h:     {stats['new_items_last_48h']}")
    lines.append(f"  with_title:             {stats['with_title']}")
    lines.append(f"  with_url:               {stats['with_url']}")
    lines.append(f"  with_zh_one_liner:     {stats['with_zh_one_liner']}   (AI Chinese one-liner)")
    lines.append(f"  with_zh_summary:       {stats['with_zh_summary']}   (AI Chinese detailed summary)")
    lines.append(f"  with_metadata_summary: {stats['with_metadata_summary']}   (English/来源 summary)")
    lines.append(f"  missing_all_summary:   {stats['missing_all_summary']}   (no usable summary)")
    lines.append(f"  with_snapshot:          {stats['with_snapshot']}")
    lines.append(f"  with_insight_card:      {stats['with_insight_card']}")
    lines.append("")
    lines.append("## Compile Readiness (V1.0-beta.16 Phase 4.3)")
    lines.append(f"  already_compiled_items:         {stats['already_compiled_items']}")
    lines.append(f"  metadata_compile_candidates:     {stats['metadata_compile_candidates']}  (discovered + rich RSS/metadata text)")
    lines.append(f"  fulltext_compile_candidates:   {stats['fulltext_compile_candidates']}  (discovered + snapshot file, needs URL fetch)")
    lines.append("  Note: Most discovered items are metadata compile candidates — no URL fetch needed.")
    lines.append("")

    lines.append("## Status Breakdown")
    lines.append(f"  discovered:  {stats['status_discovered']}")
    lines.append(f"  fetched:     {stats['status_fetched']}")
    lines.append(f"  compiled:    {stats['status_compiled']}")
    lines.append("")

    if stats.get("oldest_first_seen_at"):
        lines.append(f"  oldest_first_seen_at: {stats['oldest_first_seen_at']}")
        lines.append(f"  newest_first_seen_at: {stats['newest_first_seen_at']}")
        lines.append("")

    lines.append("## Top Sources by New Items (24h)")
    for source_key, count in stats["top_sources_by_new_items_24h"]:
        lines.append(f"  {source_key}: {count}")
    lines.append("")

    lines.append("## By-Source Breakdown")
    for source_key in sorted(stats["by_source"].keys()):
        d = stats["by_source"][source_key]
        if d["total"] == 0:
            continue
        lines.append(f"  {source_key}:")
        lines.append(f"    total={d['total']} new_24h={d['new_24h']} new_48h={d['new_48h']}")
        lines.append(f"    with_title={d['with_title']} with_url={d['with_url']}")
        lines.append(f"    with_zh_one_liner={d['with_zh_one_liner']} "
                     f"with_zh_summary={d['with_zh_summary']} "
                     f"with_metadata_summary={d['with_metadata_summary']} "
                     f"missing_all_summary={d['missing_all_summary']}")
        lines.append(f"    with_snapshot={d['with_snapshot']} with_card={d['with_card']}")
        lines.append(f"    discovered={d['discovered']} fetched={d['fetched']} compiled={d['compiled']}")
    lines.append("")

    lines.append("=" * 70)
    return "\n".join(lines)


def sample_today_items(db, limit: int = 20) -> list[dict]:
    """Sample items from the today radar window (last 24h)."""
    from app.models import SourceItem
    from app.application.content.content_snapshot import get_snapshot_path
    import json

    cutoff = datetime.utcnow() - timedelta(hours=24)

    items = (
        db.query(SourceItem)
        .filter(
            (SourceItem.first_seen_at >= cutoff) | (SourceItem.last_seen_at >= cutoff)
        )
        .order_by(SourceItem.first_seen_at.desc())
        .limit(limit * 2)  # over-fetch, filter later
        .all()
    )

    samples = []
    for item in items:
        if len(samples) >= limit:
            break

        raw = item.raw_metadata_json
        has_summary = False
        summary_status = None
        if raw:
            try:
                meta = json.loads(raw)
                has_summary = bool(meta.get("zh_summary") or meta.get("summary_zh"))
                summary_status = meta.get("summary_status")
            except Exception:
                pass

        has_snapshot = get_snapshot_path(item.id).exists()
        insight_state, insight_label = _get_insight_state(item, raw)

        samples.append({
            "id": item.id,
            "source_key": item.source_key,
            "title": item.title,
            "url": item.url,
            "status": item.status,
            "published_at": str(item.published_at) if item.published_at else None,
            "first_seen_at": item.first_seen_at.isoformat() if item.first_seen_at else None,
            "last_seen_at": item.last_seen_at.isoformat() if item.last_seen_at else None,
            "has_summary": has_summary,
            "summary_status": summary_status,
            "has_snapshot": has_snapshot,
            "insight_card_id": item.insight_card_id,
            "insight_state": insight_state,
            "insight_label": insight_label,
        })

    return samples


def _get_insight_state(item, raw: str | None) -> tuple[str, str]:
    """Get insight state for display."""
    if not raw:
        return ("missing", "未生成")
    try:
        meta = json.loads(raw)
    except Exception:
        return ("missing", "未生成")

    if item.insight_card_id:
        insight_status = meta.get("insight_status", "")
        if insight_status == "generated":
            return ("generated", "已生成")
        return ("has_card", "已有洞察卡")

    summary_status = meta.get("summary_status")
    summary_basis = meta.get("summary_basis")

    if summary_status == "generated" and summary_basis == "html_snapshot":
        return ("eligible", "可生成")

    if summary_status == "generated":
        return ("has_summary", "已有摘要")

    return ("missing", "未生成")


def format_samples(samples: list[dict]) -> str:
    lines = []
    lines.append("")
    lines.append("## Today Radar Sample (last 24h)")
    lines.append("")
    for i, s in enumerate(samples, 1):
        lines.append(f"[{i}] id={s['id']} source_key={s['source_key']}")
        lines.append(f"    title: {str(s['title'] or '')[:60]}")
        lines.append(f"    url:   {str(s['url'] or '')[:70]}")
        lines.append(f"    status={s['status']} first_seen={s['first_seen_at'][:16] if s['first_seen_at'] else '?'}")
        lines.append(f"    summary={s['has_summary']} snapshot={s['has_snapshot']} insight={s['insight_label']}")
    return "\n".join(lines)


def main() -> int:
    print("Loading database...")
    try:
        from app.db import SessionLocal, init_db
    except Exception as e:
        print(f"[ERROR] Failed to import app modules: {e}")
        return 1

    init_db()
    db = SessionLocal()

    try:
        print("[AUDIT] Analyzing dataset...")
        stats = analyze_dataset(db)
        print(format_report(stats))

        print("[AUDIT] Sampling today items...")
        samples = sample_today_items(db, limit=20)
        print(format_samples(samples))

        # Summary judgment
        print("")
        print("## Quality Judgment")
        total = stats["total_source_items"]
        new_24h = stats["new_items_last_24h"]
        with_card = stats["with_insight_card"]
        discovered = stats["status_discovered"]
        already_compiled = stats["already_compiled_items"]
        metadata_candidates = stats["metadata_compile_candidates"]
        fulltext_candidates = stats["fulltext_compile_candidates"]
        processing_candidates = metadata_candidates + fulltext_candidates

        print(f"  Total SourceItems: {total}")
        print(f"  New items (24h): {new_24h} ({100*new_24h/max(total,1):.1f}%)")
        print(f"  Already compiled/with card: {already_compiled}")
        print(f"  Metadata compile candidates: {metadata_candidates}")
        print(f"  Fulltext compile candidates: {fulltext_candidates}")
        print(f"  Processing candidates: {processing_candidates}")
        print(f"  Items needing processing: {discovered}")
        print("")
        print("  --- Summary Coverage ---")
        zh_one_liner = stats["with_zh_one_liner"]
        zh_summary = stats["with_zh_summary"]
        metadata_summary = stats["with_metadata_summary"]
        missing_all = stats["missing_all_summary"]
        print(f"  Chinese one-liner coverage: {zh_one_liner}/{total} ({100*zh_one_liner/max(total,1):.1f}%)")
        print(f"  Chinese summary coverage: {zh_summary}/{total} ({100*zh_summary/max(total,1):.1f}%)")
        print(f"  Source metadata summary coverage: {metadata_summary}/{total} ({100*metadata_summary/max(total,1):.1f}%)")
        print(f"  Missing all summary: {missing_all}/{total} ({100*missing_all/max(total,1):.1f}%)")
        print("")
        if metadata_candidates > 0:
            print(f"  i {metadata_candidates} items can use metadata compile (no URL fetch needed)")
        if fulltext_candidates > 0:
            print(f"  i {fulltext_candidates} items need URL fetch for fulltext compile")
        if metadata_summary > 0:
            print(f"  i {metadata_summary} items have English/source metadata -- suitable for Chinese summary generation")
        if zh_summary == 0 and metadata_summary > 0:
            print(f"  -> Next step: run generate-summaries on metadata compile candidates")
        if missing_all > metadata_summary * 2:
            print(f"  ! {missing_all} items missing all summary -- some sources may need better RSS/HTML extraction")
        if with_card > 0:
            print(f"  [*] {with_card} items already have InsightCards")

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
