"""Daily cycle orchestration (P3): fetch increment → summarize → report → audio.

Runs the core daily loop end-to-end. Idempotent and best-effort per step (one
step's failure is recorded but does not abort the rest). There is no in-app
scheduler by design — an external scheduler (Windows Task Scheduler / cron)
invokes ``scripts/run_daily_cycle.py`` at the daily anchor (08:00). The radar's
display anchor is deterministic, so it stays correct regardless of when (or
whether) this ran.

Steps:
1. fetch  — daily-increment fetch of due sources (sync; reuses discovery_runs).
2. summary — summarize the whole increment's missing items (select_increment_summary_targets).
3. report — generate + persist today's core report (LLM, gated by DAILY_REPORT_ENABLED).
4. audio  — (opt-in) synthesize the report narration via MiMo TTS.
Finally records a 'last cycle run' marker (offline-gap / history awareness).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DailyCycleResult:
    dry_run: bool
    fetch_due: int = 0
    fetch_started: int = 0
    summary_targets: int = 0
    summary_completed: int = 0
    report_status: str = "skipped"
    audio_status: str = "skipped"
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
    do_audio: bool = False,
    max_sources: int = 50,
) -> DailyCycleResult:
    """Run (or dry-run) the daily cycle. See module docstring."""
    result = DailyCycleResult(dry_run=dry_run)

    # 1. Fetch the daily increment (due sources only).
    if do_fetch:
        try:
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
        except Exception as exc:  # best-effort
            result.errors.append(f"fetch: {exc}")

    # 2. Summarize the whole increment's missing items.
    if do_summary:
        try:
            from app.application.radar.background_summary import (
                select_increment_summary_targets,
                run_summary_batch_in_background,
            )
            targets = select_increment_summary_targets(db)
            result.summary_targets = len(targets)
            if not dry_run and targets:
                run_summary_batch_in_background(targets)
                db.expire_all()
            _, result.summary_completed = _summary_coverage(db)
            result.steps.append(
                f"summary: targets={len(targets)} covered={result.summary_completed}"
                + (" (dry-run)" if dry_run else "")
            )
        except Exception as exc:
            result.errors.append(f"summary: {exc}")

    # 3. Generate + persist the core report.
    if do_report:
        try:
            if dry_run:
                result.report_status = "would_generate"
            else:
                from app.application.radar.daily_report import generate_daily_report
                from app.application.radar.daily_report_store import save_daily_report

                report = generate_daily_report(db, apply=True)
                result.report_status = report.status
                if report.status == "generated":
                    save_daily_report(report)
            result.steps.append(f"report: {result.report_status}")
        except Exception as exc:
            result.errors.append(f"report: {exc}")

    # 4. (opt-in) Synthesize the report narration.
    if do_audio:
        try:
            if dry_run:
                result.audio_status = "would_generate"
            else:
                result.audio_status = _generate_audio()
            result.steps.append(f"audio: {result.audio_status}")
        except Exception as exc:
            result.errors.append(f"audio: {exc}")

    # 5. Record the completed run (offline-gap / history awareness).
    if not dry_run:
        try:
            from app.application.radar.cycle_state import set_last_cycle_run

            set_last_cycle_run(extra={
                "report_status": result.report_status,
                "summary_targets": result.summary_targets,
                "summary_completed": result.summary_completed,
            })
        except Exception as exc:
            result.errors.append(f"marker: {exc}")

    return result


def _generate_audio() -> str:
    """Best-effort: build the broadcast script from today's saved core report and
    synthesize it via MiMo TTS. Returns the resulting job status."""
    from app.application.radar.daily_report_card import build_daily_report_card
    from app.application.radar.daily_report_store import load_daily_report
    from app.application.radar.daily_broadcast import build_core_report_broadcast_script
    from app.application.radar.daily_audio_jobs import (
        enqueue_daily_audio_job,
        run_daily_audio_job,
    )
    from app.application.radar.mimo_tts import MiMoTTSSettings
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        card = build_daily_report_card(db)
    finally:
        db.close()

    core = load_daily_report(card.date_label)
    if core is None:
        return "no_report"
    script = build_core_report_broadcast_script(core)
    settings = MiMoTTSSettings.from_env()
    enq = enqueue_daily_audio_job(
        script,
        script_basis="今日核心报告",
        voice=settings.voice,
        style=settings.style,
        report_version=core.get("version_id"),
    )
    if enq.should_start:
        run_daily_audio_job(enq.job.job_id)
    return "generated"
