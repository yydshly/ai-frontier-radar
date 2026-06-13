"""radar — Adapter: ShareReportSnapshot → VideoSourceSnapshot.

This adapter is the ONLY entry point from radar business logic into content_video.
It maps radar-specific ShareReportSnapshot fields to the generic VideoSourceSnapshot
schema that content_video.service.generate_video() consumes.

Direction constraint:
  ✓ adapter may import content_video
  ✗ content_video may NOT import adapter or radar
"""
from __future__ import annotations

from app.application.content_video.models import VideoSourceSnapshot, VideoSourceSection
from app.application.radar.share_snapshot import ShareReportSnapshot


def build_video_source_snapshot_from_share_report(
    snapshot: ShareReportSnapshot,
) -> VideoSourceSnapshot:
    """Convert a radar ShareReportSnapshot to a generic VideoSourceSnapshot.

    Mapping rules
    ────────────
    VideoSourceSnapshot.source_key = snapshot.share_key
    VideoSourceSnapshot.title     = snapshot.title
    VideoSourceSnapshot.subtitle  = snapshot.headline
    VideoSourceSnapshot.date_label = snapshot.date_label
    VideoSourceSnapshot.summary   = snapshot.overview or snapshot.headline
    VideoSourceSnapshot.sections  = highlights → VideoSourceSection[]
    VideoSourceSnapshot.takeaways = snapshot.takeaways
    VideoSourceSnapshot.source_url = snapshot.report_url
    VideoSourceSnapshot.version_id = snapshot.report_version_id
    VideoSourceSnapshot.metadata  = snapshot.metadata (pass-through)
    """
    sections: list[VideoSourceSection] = [
        VideoSourceSection(
            title=h.title,
            summary=h.summary,
            key_points=[],
            why_it_matters=h.why_it_matters,
            source_name=h.source_name,
            source_url=h.source_url,
        )
        for h in snapshot.highlights
    ]

    # Build a safe summary: prefer overview, fall back to headline
    summary_text = snapshot.overview if snapshot.overview else snapshot.headline

    return VideoSourceSnapshot(
        source_key=snapshot.share_key,
        title=snapshot.title,
        subtitle=snapshot.headline,
        date_label=snapshot.date_label,
        summary=summary_text,
        sections=sections,
        takeaways=snapshot.takeaways,
        source_url=snapshot.report_url,
        version_id=snapshot.report_version_id,
        metadata=snapshot.metadata,
    )
