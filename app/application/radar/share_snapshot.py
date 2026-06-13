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

    # Build highlights from view.highlights
    highlights: list[ShareReportHighlight] = []
    for h in (view.highlights or []):
        text = getattr(h, "text", "") or ""
        highlights.append(
            ShareReportHighlight(
                title=text[:100] if text else "重点内容",
                summary=text,
                why_it_matters=None,
                source_name=None,
                source_url=None,
            )
        )

    # Takeaways: first 3 highlights as key takeaways
    takeaways = [h.summary for h in highlights[:3] if h.summary]

    share_key = f"radar_{date_label}" if date_label else "radar_today"

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
        metadata={},
    )


def build_history_share_snapshot(
    db,
    date_label: str,
) -> ShareReportSnapshot:
    """Build ShareReportSnapshot for a specific historical date."""
    return build_today_share_snapshot(db, date_label)
