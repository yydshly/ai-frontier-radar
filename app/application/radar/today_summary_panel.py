"""Read-only Today's Summary panel for the radar today sidebar.

Provides the core report status and today's latest generated audio
for the compact "今日总结" sidebar module.

Does NOT call any LLM. Does NOT generate audio. Does NOT write anything.
"""
from dataclasses import dataclass
from datetime import datetime

from app.application.radar.daily_audio_jobs import (
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    list_daily_audio_jobs,
    select_daily_audio_job,
)
from app.application.radar.daily_report_store import load_daily_report


@dataclass(frozen=True)
class TodaySummaryHighlight:
    text: str
    references: tuple[dict, ...] = ()


def _today_date_label() -> str:
    """Return the UTC date label used by the daily report builders."""
    return datetime.utcnow().strftime("%Y-%m-%d")


def _compact_report_text(*parts: str | None, max_chars: int = 240) -> str | None:
    """Join non-empty parts, collapse whitespace, truncate with ellipsis."""
    text = " ".join(
        " ".join(p.split()) for p in parts if isinstance(p, str) and p.strip()
    )
    if not text:
        return None
    if len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "…"
    return text


@dataclass(frozen=True)
class TodaySummaryPanelView:
    """Read-only view of today's final deliverables for the sidebar module."""
    date_label: str
    has_core_report: bool
    core_report_title: str | None
    core_report_overview: str | None
    core_report_highlights: tuple[TodaySummaryHighlight, ...]
    core_report_excerpt: str | None
    generated_at: str | None
    report_version: str | None
    report_is_stale: bool
    core_report_url: str
    has_audio: bool
    audio_status: str
    audio_job_id: str | None
    audio_completed_chunks: int
    audio_chunk_count: int
    audio_error: str | None
    audio_url: str | None
    audio_title: str | None
    audio_page_url: str


def build_today_summary_panel_view(
    *,
    date_label: str | None = None,
    current_input_fingerprint: str | None = None,
) -> TodaySummaryPanelView:
    """Build the today summary panel view for the radar today sidebar.

    Reads:
    - The latest generated core report for today (if any).
    - The latest generated audio for today (if any).
    """
    date_label = date_label or _today_date_label()

    # ── Core report ────────────────────────────────────────────
    core_report = load_daily_report(date_label)
    has_core_report = (
        core_report is not None
        and core_report.get("status") == "generated"
    )
    core_report_title: str | None = None
    core_report_overview: str | None = None
    core_report_highlights: tuple[TodaySummaryHighlight, ...] = ()
    core_report_excerpt: str | None = None
    generated_at: str | None = None
    core_report_url = (
        f"/radar/daily-report#daily-core-report"
        if has_core_report
        else "/radar/daily-report"
    )
    if has_core_report and core_report:
        core_report_title = core_report.get("title") or "今日核心报告"
        overview = core_report.get("overview")
        core_report_overview = (
            " ".join(overview.split())
            if isinstance(overview, str) and overview.strip()
            else None
        )
        highlights = core_report.get("highlights", [])
        highlight_parts: list[str] = []
        for highlight in highlights[:3]:
            if isinstance(highlight, str):
                highlight_parts.append(highlight)
            elif isinstance(highlight, dict):
                text = highlight.get("text")
                if isinstance(text, str) and text.strip():
                    highlight_parts.append(text)
        references = core_report.get("highlight_references", [])
        core_report_highlights = tuple(
            TodaySummaryHighlight(
                text=text,
                references=tuple(
                    references[index]
                    if index < len(references)
                    and isinstance(references[index], list)
                    else []
                ),
            )
            for index, text in enumerate(highlight_parts)
        )
        highlight_text = "；".join(highlight_parts)
        core_report_excerpt = _compact_report_text(
            core_report_overview,
            highlight_text,
            max_chars=240,
        )
        generated_value = core_report.get("generated_at")
        generated_at = (
            generated_value.replace("T", " ")
            if isinstance(generated_value, str) and generated_value.strip()
            else None
        )

    # ── Audio: latest generated audio for today ───────────────
    all_jobs = list_daily_audio_jobs(limit=50)
    report_version = (
        core_report.get("version_id")
        if has_core_report and core_report
        else None
    )
    stored_fingerprint = (
        core_report.get("input_fingerprint")
        if has_core_report and core_report
        else None
    )
    report_is_stale = bool(
        current_input_fingerprint
        and stored_fingerprint
        and current_input_fingerprint != stored_fingerprint
    )
    latest_audio = select_daily_audio_job(
        all_jobs,
        date_label=date_label,
        report_version=report_version,
    )
    has_audio = latest_audio is not None
    matching_jobs = [
        job
        for job in all_jobs
        if job.date_label == date_label
        and (
            not report_version
            or job.report_version == report_version
        )
    ]
    latest_matching_job = matching_jobs[0] if matching_jobs else None
    if has_audio:
        audio_status = "generated"
        audio_job_id = latest_audio.job_id
    elif (
        latest_matching_job
        and latest_matching_job.status in {JOB_STATUS_QUEUED, JOB_STATUS_RUNNING}
    ):
        audio_status = latest_matching_job.status
        audio_job_id = latest_matching_job.job_id
    elif latest_matching_job and latest_matching_job.status == JOB_STATUS_FAILED:
        audio_status = "failed"
        audio_job_id = latest_matching_job.job_id
    else:
        audio_status = "missing"
        audio_job_id = None
    status_job = latest_audio or latest_matching_job
    audio_completed_chunks = status_job.completed_chunks if status_job else 0
    audio_chunk_count = status_job.chunk_count if status_job else 0
    audio_error = status_job.error if status_job else None
    audio_url = latest_audio.audio_url if has_audio else None
    audio_title = latest_audio.title if has_audio else None
    audio_page_url = "/radar/daily-report/broadcast"
    if report_version:
        audio_page_url += f"?version={report_version}"

    return TodaySummaryPanelView(
        date_label=date_label,
        has_core_report=has_core_report,
        core_report_title=core_report_title,
        core_report_overview=core_report_overview,
        core_report_highlights=core_report_highlights,
        core_report_excerpt=core_report_excerpt,
        generated_at=generated_at,
        report_version=report_version,
        report_is_stale=report_is_stale,
        core_report_url=core_report_url,
        has_audio=has_audio,
        audio_status=audio_status,
        audio_job_id=audio_job_id,
        audio_completed_chunks=audio_completed_chunks,
        audio_chunk_count=audio_chunk_count,
        audio_error=audio_error,
        audio_url=audio_url,
        audio_title=audio_title,
        audio_page_url=audio_page_url,
    )
