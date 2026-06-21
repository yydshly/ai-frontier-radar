"""radar — ShareReportSnapshot: structured core-report snapshot for share pages.

This layer sits between the H5 share view data and the generic content_video
module. It provides a stable, radar-specific snapshot of the share page's
core report that can be converted to VideoSourceSnapshot.

Data source constraints
───────────────────────
ShareReportSnapshot is built from data already available in the share page:
  - view.report (the core report dict from daily_report_store)
  - view.highlights (ShareHighlight list from share.py)
  - view.stats (ShareStats)
  - date_label
  - audio_job

It does NOT query SourceItem, InsightCard, daily_cycle, or RSS raw content.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ShareReportHighlight:
    """One highlight within the share report."""
    title: str
    summary: str
    why_it_matters: str | None = None
    source_name: str | None = None
    source_url: str | None = None


@dataclass(frozen=True)
class ShareReportSnapshot:
    """A frozen snapshot of the share page's core report.

    This is the canonical data source for video generation from a share page.
    It must be buildable purely from data already in the share page view.
    """
    share_key: str          # e.g. "radar_today", "radar_2026-06-12"
    date_label: str
    report_version_id: str | None
    title: str              # report title
    headline: str          # short one-liner / overview
    overview: str          # detailed overview text
    highlights: list[ShareReportHighlight]
    takeaways: list[str]
    report_url: str | None = None
    generated_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


import re as _re

_SENT_END_RE = _re.compile(r"[^。！？；]*[。！？；]")


def _trim_to_sentences(text: str, *, max_chars: int = 120) -> str:
    """Return whole leading sentences of `text` up to ~max_chars (never cut mid
    sentence). Falls back to a hard slice if the first sentence already exceeds it.
    """
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    out = ""
    for m in _SENT_END_RE.finditer(text):
        out += m.group()
        if len(out) >= max_chars:  # include the sentence that reaches the target
            break
    return out or text[:max_chars]


def build_today_share_snapshot(
    db,
    date_label: str | None = None,
) -> ShareReportSnapshot:
    """Build ShareReportSnapshot for today (or a specific date_label).

    Reads from daily_report_store and share.py helpers — no SourceItem queries.
    """
    from app.application.radar.daily_report_store import (
        load_daily_report,
        load_final_daily_report,
    )
    from app.application.radar.share import build_share_view

    if date_label is None:
        from app.application.radar.daily_scope import latest_completed_date_label
        date_label = latest_completed_date_label()

    view = build_share_view(db, date_label)
    report = view.report

    if report:
        title = str(report.get("title") or "AI 前沿雷达").strip()
        overview = str(report.get("overview") or "").strip()
        version_id = report.get("version_id")
    else:
        title = "AI 前沿雷达"
        overview = ""
        version_id = None

    # Map item_id -> detailed description (zh_summary) from the day's articles,
    # so each highlight (one-liner) can be enriched with the detail of its 依据.
    detail_by_item: dict[int, str] = {}
    for a in (view.important or []):
        if getattr(a, "description", None):
            detail_by_item[a.item_id] = a.description
    for g in (view.other_groups or []):
        for a in g.items:
            if getattr(a, "description", None):
                detail_by_item[a.item_id] = a.description

    # Build highlights from view.highlights, enriched with the 依据 detail.
    highlights: list[ShareReportHighlight] = []
    for h in (view.highlights or []):
        text = getattr(h, "text", "") or ""
        references = list(getattr(h, "references", []) or [])
        primary_reference = references[0] if references else None
        detail = ""
        for rf in references:
            d = detail_by_item.get(getattr(rf, "item_id", None))
            if d:
                detail = _trim_to_sentences(d, max_chars=120)
                break
        highlights.append(
            ShareReportHighlight(
                title=(text or "重点内容"),          # the one-liner headline
                summary=(detail or text),            # the detailed 依据 概述 (body)
                why_it_matters=None,
                source_name=(
                    getattr(primary_reference, "title", None)
                    if primary_reference is not None
                    else None
                ),
                source_url=(
                    getattr(primary_reference, "url", None)
                    if primary_reference is not None
                    else None
                ),
            )
        )

    raw_takeaways = []
    if report:
        raw_takeaways = (
            report.get("takeaways")
            or report.get("supporting_notes")
            or []
        )
    takeaways = [
        str(item).strip()
        for item in raw_takeaways
        if str(item).strip()
    ]
    # NOTE: do NOT fall back to copying the highlights here. Doing so made the
    # video repeat every core observation a second time as "补充观察". When the
    # report has no distinct takeaways, leave it empty so the video skips the
    # supporting section entirely (tighter, no duplication).

    share_key = f"radar_{date_label}" if date_label else "radar_today"

    # Carry the day's stats so the video cover can render a real bar chart.
    metadata: dict[str, Any] = {}
    if view.stats is not None:
        metadata["stats"] = {
            "new": view.stats.new_items,
            "summarized": view.stats.summarized,
            "important": view.stats.important,
            "sources": view.stats.sources,
        }

    return ShareReportSnapshot(
        share_key=share_key,
        date_label=date_label,
        report_version_id=version_id,
        title=title,
        headline=overview[:120] if overview else "今日 AI 前沿要闻",
        overview=overview,
        highlights=highlights,
        takeaways=takeaways,
        report_url=None,
        generated_at=None,
        metadata=metadata,
    )


def build_history_share_snapshot(
    db,
    date_label: str,
) -> ShareReportSnapshot:
    """Build ShareReportSnapshot for a specific historical date."""
    return build_today_share_snapshot(db, date_label)
