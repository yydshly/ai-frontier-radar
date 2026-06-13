"""Daily cycle orchestration: finalize completed periods → process live period.

Runs the core daily loop end-to-end. Idempotent and best-effort per step (one
step's failure is recorded but does not abort the rest). There is no in-app
scheduler by design — an external scheduler (Windows Task Scheduler / cron)
invokes ``scripts/run_daily_cycle.py`` at the daily anchor (08:00). The radar's
display anchor is deterministic, so it stays correct regardless of when (or
whether) this ran.

Steps:
1. finalization — catch up completed anchor periods, including summaries,
   immutable formal report, article snapshots and default audio.
2. fetch — daily-increment fetch of due sources for the new live period.
3. summary — summarize the live period's missing items.
Finally records a 'last cycle run' marker (offline-gap / history awareness).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Any

ProgressCallback = Callable[[str, dict[str, Any]], None]


@dataclass
class DailyCycleResult:
    dry_run: bool
    fetch_due: int = 0
    fetch_started: int = 0
    summary_targets: int = 0
    summary_completed: int = 0
    report_status: str = "skipped"
    audio_status: str = "skipped"
    finalized_dates: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _summary_coverage(db) -> tuple[int, int]:
    """(increment_total, with_complete_summary)."""
    import json
    from app.application.radar.daily_scope import recent_valid_items_query, daily_anchor

    rows = recent_valid_items_query(db, since=daily_anchor()).all()
    done = 0
    for it in rows:
        try:
            raw = json.loads(it.raw_metadata_json or "{}")
        except (TypeError, ValueError):
            raw = {}
        if isinstance(raw, dict) and str(raw.get("zh_one_liner") or "").strip() and str(raw.get("zh_summary") or "").strip():
            done += 1
    return len(rows), done


def run_daily_cycle(
    db,
    *,
    dry_run: bool = True,
    do_fetch: bool = True,
    do_summary: bool = True,
    do_report: bool = True,
    do_audio: bool = True,
    max_sources: int = 50,
    progress_callback: ProgressCallback | None = None,
) -> DailyCycleResult:
    """Run (or dry-run) the daily cycle. See module docstring."""

    def _progress(step: str, **payload) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(step, payload)
        except Exception:
            # progress logging must never break business flow
            pass

    result = DailyCycleResult(dry_run=dry_run)

    _progress(
        "cycle_start",
        dry_run=dry_run,
        do_fetch=do_fetch,
        do_summary=do_summary,
        do_report=do_report,
        do_audio=do_audio,
        max_sources=max_sources,
    )

    # 1. Finalize all recently completed periods before opening the live cycle.
    if do_report:
        try:
            _progress("finalization_check_start", include_audio_incomplete=do_audio)

            from app.application.radar.daily_finalization import (
                finalize_daily_report,
                pending_finalization_dates,
            )
            from app.application.radar.settings import (
                get_daily_finalization_backfill_days,
            )

            pending_dates = pending_finalization_dates(
                max_days=get_daily_finalization_backfill_days(),
                include_audio_incomplete=do_audio,
            )
            _progress("finalization_pending_dates", count=len(pending_dates), dates=pending_dates)

            if dry_run:
                result.report_status = "would_generate"
                result.audio_status = (
                    "would_generate" if pending_dates and do_audio else "skipped"
                )
                result.steps.append(
                    "report: finalization "
                    + (", ".join(pending_dates) if pending_dates else "up-to-date")
                    + " (dry-run)"
                )
            else:
                statuses: list[str] = []
                audio_statuses: list[str] = []
                for date_label in pending_dates:
                    _progress("finalization_date_start", date=date_label, generate_audio=do_audio)
                    finalized = finalize_daily_report(
                        db,
                        date_label,
                        generate_audio=do_audio,
                    )
                    statuses.append(finalized.status)
                    audio_statuses.append(finalized.audio_status)
                    if finalized.status in {"finalized", "already_finalized"}:
                        result.finalized_dates.append(date_label)
                    result.errors.extend(
                        f"finalization {date_label}: {error}"
                        for error in finalized.errors
                    )
                    _progress(
                        "finalization_date_done",
                        date=date_label,
                        status=finalized.status,
                        audio_status=finalized.audio_status,
                        error_count=len(finalized.errors),
                    )
                result.report_status = (
                    "finalized"
                    if "finalized" in statuses
                    else (statuses[-1] if statuses else "up_to_date")
                )
                result.audio_status = (
                    audio_statuses[-1] if audio_statuses else "up_to_date"
                )
                result.steps.append(
                    "report: finalization "
                    + (
                        ", ".join(
                            f"{label}={status}"
                            for label, status in zip(pending_dates, statuses)
                        )
                        if pending_dates
                        else "up-to-date"
                    )
                )
        except Exception as exc:
            result.errors.append(f"finalization: {exc}")
            _progress("finalization_error", error=str(exc))
    else:
        _progress("finalization_skipped", reason="do_report_false")

    # 2. Fetch the live daily increment (due sources only).
    if do_fetch:
        try:
            _progress("fetch_start", max_sources=max_sources, dry_run=dry_run)

            from app.application.sources.discovery_runs import (
                run_source_discovery,
                SourceDiscoveryRunSettings,
                DAILY_INCREMENT_MODE,
            )
            r = run_source_discovery(
                db,
                SourceDiscoveryRunSettings(
                    mode=DAILY_INCREMENT_MODE, dry_run=dry_run, max_sources=max_sources
                ),
                background_tasks=None,
            )
            result.fetch_due = r.eligible_sources
            result.fetch_started = r.started
            result.steps.append(
                f"fetch: due={r.eligible_sources} started={r.started}"
                + (" (dry-run)" if dry_run else "")
            )
            _progress(
                "fetch_done",
                eligible_sources=r.eligible_sources,
                started=r.started,
            )
        except Exception as exc:  # best-effort
            result.errors.append(f"fetch: {exc}")
            _progress("fetch_error", error=str(exc))
    else:
        _progress("fetch_skipped", reason="do_fetch_false")

    # 3. Summarize the live increment's missing items.
    if do_summary:
        try:
            _progress("summary_select_start")

            from app.application.radar.background_summary import (
                select_increment_summary_targets,
                run_summary_batch_in_background,
            )
            targets = select_increment_summary_targets(db)
            result.summary_targets = len(targets)
            _progress("summary_targets_selected", count=len(targets))

            if not dry_run and targets:
                _progress("summary_batch_start", count=len(targets))
                run_summary_batch_in_background(targets)
                db.expire_all()
                _progress("summary_batch_done", count=len(targets))

            _, result.summary_completed = _summary_coverage(db)
            _progress(
                "summary_coverage_done",
                targets=len(targets),
                completed=result.summary_completed,
            )
            result.steps.append(
                f"summary: targets={len(targets)} covered={result.summary_completed}"
                + (" (dry-run)" if dry_run else "")
            )
        except Exception as exc:
            result.errors.append(f"summary: {exc}")
            _progress("summary_error", error=str(exc))
    else:
        _progress("summary_skipped", reason="do_summary_false")

    # 4. Record the completed run (offline-gap / history awareness).
    if not dry_run:
        try:
            _progress("marker_start")

            from app.application.radar.cycle_state import set_last_cycle_run

            set_last_cycle_run(extra={
                "report_status": result.report_status,
                "summary_targets": result.summary_targets,
                "summary_completed": result.summary_completed,
                "finalized_dates": result.finalized_dates,
            })
            _progress("marker_done")
        except Exception as exc:
            result.errors.append(f"marker: {exc}")
            _progress("marker_error", error=str(exc))
    else:
        _progress("marker_skipped", reason="dry_run")

    _progress(
        "cycle_done",
        fetch_due=result.fetch_due,
        fetch_started=result.fetch_started,
        summary_targets=result.summary_targets,
        summary_completed=result.summary_completed,
        report_status=result.report_status,
        audio_status=result.audio_status,
        error_count=len(result.errors),
    )

    return result
