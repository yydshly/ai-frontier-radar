"""Formal daily-report finalization for completed 08:00 anchor periods."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from app.application.radar.daily_scope import (
    anchor_window_for_date,
    latest_completed_date_label,
)
from app.models import Source, SourceItem


@dataclass(frozen=True)
class DailyFinalizationResult:
    date_label: str
    status: str
    summary_completed: int = 0
    summary_failed: int = 0
    report_version: str | None = None
    audio_status: str = "skipped"
    message: str = ""
    errors: list[str] = field(default_factory=list)


def pending_finalization_dates(
    *,
    now: datetime | None = None,
    max_days: int = 7,
    root_dir=None,
    include_audio_incomplete: bool = False,
) -> list[str]:
    """Return missing completed periods, oldest first, within a bounded lookback."""
    from app.application.radar.daily_report_store import load_final_daily_report

    latest = datetime.strptime(latest_completed_date_label(now), "%Y-%m-%d")
    labels = [
        (latest - timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range(max(1, max_days))
    ]
    pending: list[str] = []
    for label in reversed(labels):
        report = load_final_daily_report(label, root_dir=root_dir)
        if report is None:
            pending.append(label)
        elif (
            include_audio_incomplete
            and report.get("audio_status") != "generated"
        ):
            pending.append(label)
    return pending


def _items_in_period(db, date_label: str) -> list[SourceItem]:
    start, end = anchor_window_for_date(date_label)
    return (
        db.query(SourceItem)
        .join(Source, Source.id == SourceItem.source_id)
        .filter(
            Source.enabled.is_(True),
            SourceItem.first_seen_at >= start,
            SourceItem.first_seen_at < end,
            SourceItem.url.isnot(None),
            SourceItem.url != "",
            SourceItem.title.isnot(None),
            SourceItem.title != "",
        )
        .order_by(SourceItem.first_seen_at.desc(), SourceItem.id.desc())
        .all()
    )


def _metadata(item: SourceItem) -> dict[str, Any]:
    try:
        value = json.loads(item.raw_metadata_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _has_complete_summary(item: SourceItem) -> bool:
    raw = _metadata(item)
    return bool(
        str(raw.get("zh_one_liner") or "").strip()
        and str(raw.get("zh_summary") or "").strip()
    )


def _complete_missing_summaries(
    db,
    items: list[SourceItem],
    *,
    limit: int,
) -> tuple[int, int]:
    """Synchronously fill missing summaries without overwriting existing text."""
    from app.application.candidates.one_liner import (
        CandidateOneLinerService,
        get_one_liner_settings,
    )

    targets = [item for item in items if not _has_complete_summary(item)][:limit]
    if not targets:
        return 0, 0

    settings = get_one_liner_settings()
    service = CandidateOneLinerService(db, settings=settings)
    targets = targets[:min(limit, settings.max_per_run, settings.max_per_day)]
    completed = failed = 0
    for item in targets:
        try:
            service.generate_for_item(
                item,
                fill_missing_summary=True,
                force=False,
            )
            db.refresh(item)
            if _has_complete_summary(item):
                completed += 1
            else:
                failed += 1
        except Exception:
            db.rollback()
            failed += 1
    return completed, failed


def _build_article_snapshots(db, items: list[SourceItem]) -> list[dict[str, Any]]:
    from app.application.candidates.display import build_candidate_display_card

    source_keys = {item.source_key for item in items}
    source_names = {
        source.source_key: source.name
        for source in db.query(Source).filter(Source.source_key.in_(source_keys)).all()
    } if source_keys else {}

    snapshots: list[dict[str, Any]] = []
    for item in items:
        card = build_candidate_display_card(item)
        raw = _metadata(item)
        snapshots.append({
            "item_id": item.id,
            "title": card.title,
            "zh_one_liner": (
                str(raw.get("zh_one_liner") or "").strip() or None
            ),
            "zh_summary": (
                str(raw.get("zh_summary") or "").strip() or None
            ),
            "source_name": source_names.get(item.source_key, item.source_key),
            "source_key": item.source_key,
            "url": card.url,
            "insight_card_id": item.insight_card_id,
            "first_seen_at": (
                item.first_seen_at.isoformat()
                if item.first_seen_at is not None
                else None
            ),
        })
    return snapshots


def _generate_final_audio(report: dict[str, Any]) -> tuple[str, str | None]:
    from app.application.radar.daily_audio_jobs import (
        enqueue_daily_audio_job,
        run_daily_audio_job,
    )
    from app.application.radar.daily_broadcast import (
        build_core_report_broadcast_script,
    )
    from app.application.radar.mimo_tts import MiMoTTSSettings

    script = build_core_report_broadcast_script(report)
    settings = MiMoTTSSettings.from_env()
    result = enqueue_daily_audio_job(
        script,
        script_basis="正式日报",
        voice=settings.voice,
        style=settings.style,
        report_version=report.get("version_id"),
    )
    if result.should_start:
        run_daily_audio_job(result.job.job_id)
    from app.application.radar.daily_audio_jobs import load_daily_audio_job
    job = load_daily_audio_job(result.job.job_id) or result.job
    return job.status, job.job_id


def finalize_daily_report(
    db,
    date_label: str,
    *,
    provider=None,
    generate_audio: bool = True,
    summary_limit: int = 50,
    root_dir=None,
) -> DailyFinalizationResult:
    """Finalize one completed period. Existing final reports are never overwritten."""
    from app.application.radar.daily_report import generate_daily_report
    from app.application.radar.daily_report_store import (
        load_final_daily_report,
        save_final_daily_report,
        update_final_daily_report,
    )

    existing = load_final_daily_report(date_label, root_dir=root_dir)
    if existing is not None:
        audio_status = str(existing.get("audio_status") or "unknown")
        errors: list[str] = []
        if generate_audio and audio_status != "generated":
            try:
                audio_status, audio_job_id = _generate_final_audio(existing)
                update_final_daily_report(
                    date_label,
                    {
                        "audio_status": audio_status,
                        "audio_job_id": audio_job_id,
                    },
                    root_dir=root_dir,
                )
            except Exception as exc:
                audio_status = "failed"
                errors.append(str(exc))
                update_final_daily_report(
                    date_label,
                    {
                        "audio_status": "failed",
                        "audio_error": str(exc)[:500],
                    },
                    root_dir=root_dir,
                )
        return DailyFinalizationResult(
            date_label=date_label,
            status="already_finalized",
            report_version=existing.get("version_id"),
            audio_status=audio_status,
            message="正式日报已存在，未重复生成。",
            errors=errors,
        )

    items = _items_in_period(db, date_label)
    if not items:
        return DailyFinalizationResult(
            date_label=date_label,
            status="no_input",
            message="该周期没有可结算文章。",
        )

    summary_completed, summary_failed = _complete_missing_summaries(
        db,
        items,
        limit=summary_limit,
    )
    db.expire_all()
    items = _items_in_period(db, date_label)
    remaining_missing = sum(not _has_complete_summary(item) for item in items)
    summary_status = "completed" if remaining_missing == 0 else "partial"

    report = generate_daily_report(
        db,
        provider=provider,
        apply=True,
        date_label=date_label,
    )
    if report.status != "generated":
        return DailyFinalizationResult(
            date_label=date_label,
            status=report.status,
            summary_completed=summary_completed,
            summary_failed=summary_failed,
            message=report.message,
        )

    window_start, window_end = anchor_window_for_date(date_label)
    stored = save_final_daily_report(
        report,
        articles=_build_article_snapshots(db, items),
        window_start=window_start,
        window_end=window_end,
        root_dir=root_dir,
        summary_status=summary_status,
        audio_status="pending" if generate_audio else "skipped",
    )
    if stored is None:
        return DailyFinalizationResult(
            date_label=date_label,
            status="save_failed",
            summary_completed=summary_completed,
            summary_failed=summary_failed,
            message="正式日报保存失败。",
        )
    stored = update_final_daily_report(
        date_label,
        {
            "summary_completed": summary_completed,
            "summary_failed": summary_failed,
            "summary_missing": remaining_missing,
        },
        root_dir=root_dir,
    ) or stored

    audio_status = "skipped"
    errors: list[str] = []
    if generate_audio:
        try:
            audio_status, audio_job_id = _generate_final_audio(stored)
            update_final_daily_report(
                date_label,
                {
                    "audio_status": audio_status,
                    "audio_job_id": audio_job_id,
                },
                root_dir=root_dir,
            )
        except Exception as exc:
            audio_status = "failed"
            errors.append(str(exc))
            update_final_daily_report(
                date_label,
                {
                    "audio_status": "failed",
                    "audio_error": str(exc)[:500],
                },
                root_dir=root_dir,
            )

    return DailyFinalizationResult(
        date_label=date_label,
        status="finalized",
        summary_completed=summary_completed,
        summary_failed=summary_failed,
        report_version=stored.get("version_id"),
        audio_status=audio_status,
        message="正式日报已结算。",
        errors=errors,
    )
