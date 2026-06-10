"""Read-only scheduler status view model for the today-radar UI (V1.0-beta.3).

Aggregates the due-source plan and the stale-running diagnostic into a small,
user-facing summary for the "最近探测状态" sidebar block on /radar/today.

This module is strictly read-only:
- It only calls the read-only ``compute_due_sources()`` and
  ``build_stale_fetch_run_report()`` services.
- It never creates FetchRun rows, never triggers fetches, and never calls LLM
  services.

It deliberately exposes only user-friendly counts and a generic scheduler-mode
label. Script names and environment variables (run_due_sources_once.py, cron,
Task Scheduler, RADAR_SCHEDULER_ENABLED, AUTO_SUMMARY_MAX_PER_FETCH_RUN) are NOT
surfaced here — those live only in the operations doc.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.application.sources.due_sources import (
    REASON_NOT_DUE_YET,
    compute_due_sources,
)
from app.application.sources.stale_runs import build_stale_fetch_run_report

# Project-docs key for the scheduler operations manual (external scheduling).
SCHEDULER_OPERATIONS_DOC_KEY = "v1-beta-2-scheduler-operations"


@dataclass(frozen=True)
class RadarSchedulerStatusView:
    """User-facing scheduler status summary for the today-radar sidebar."""

    due_count: int
    skipped_count: int
    running_count: int
    unsupported_count: int
    missing_count: int
    stale_count: int
    not_due_count: int
    scheduler_mode_label: str
    scheduler_hint: str
    operations_doc_key: str


def build_radar_scheduler_status_view(db) -> RadarSchedulerStatusView:
    """Build the read-only scheduler status view from due-source + stale data.

    Read-only: does not create FetchRun, does not trigger fetches, no LLM.
    """
    plan = compute_due_sources(db)
    stale_report = build_stale_fetch_run_report(db)

    not_due_count = sum(
        1 for d in plan.skipped if d.reason == REASON_NOT_DUE_YET
    )

    return RadarSchedulerStatusView(
        due_count=plan.due_count,
        skipped_count=plan.skipped_count,
        running_count=plan.running_count,
        unsupported_count=plan.unsupported_count,
        missing_count=plan.missing_count,
        stale_count=stale_report.stale_count,
        not_due_count=not_due_count,
        scheduler_mode_label="外部配置",
        scheduler_hint=(
            "系统支持由外部定时器调用单轮调度；当前 Web 界面不直接管理系统任务。"
        ),
        operations_doc_key=SCHEDULER_OPERATIONS_DOC_KEY,
    )
