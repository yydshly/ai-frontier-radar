"""Radar routes — today's AI frontier reading view.

GET /radar/today renders a catalog + cards + reading-panel layout built
by RadarTodayService. Read-only: no fetching, no compilation, no LLM.

POST /radar/today/generate-summaries queues background summary generation for
today's items.
"""
from collections import Counter
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from urllib.parse import urlencode
import os

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.db import get_db
from app.context_processors import inject_sources_nav
from app.application.radar.today import (
    RadarTodayService,
    normalize_section_key,
    DEFAULT_HOURS,
    DEFAULT_LIMIT,
    DEFAULT_PER_PAGE,
    MIN_HOURS,
    MAX_HOURS,
    MIN_LIMIT,
    MAX_LIMIT,
    MIN_PER_PAGE,
    MAX_PER_PAGE,
    ALL_KEY,
    SUMMARY_BATCH_LIMIT,
    RECOMMENDED_LIMIT,
    RECOMMENDED_PER_SOURCE_LIMIT,
    RECOMMENDED_MAX_SCAN,
    RECOMMENDED_INSIGHT_LIMIT,
    RECOMMENDED_INSIGHT_HARD_CAP,
)
from app.application.radar.settings import (
    get_generation_settings,
    get_recommendation_settings,
    get_daily_report_enabled,
)
from app.application.source_items.item_state import summary_state_from_raw
from app.application.sources.background_fetch import SourceFetchBackgroundService
from app.application.sources.discovery_runs import (
    BOOTSTRAP_MODE,
    DAILY_INCREMENT_MODE,
    SourceDiscoveryRunSettings,
    run_source_discovery,
)
from app.application.sources.due_sources import DueSourcePlan, compute_due_sources
from app.application.sources.fetch_service import SUPPORTED_STRATEGIES
from app.models import SourceItem, Source
from app.sources.config_loader import list_sources
from app.routes.fetch_runs import safe_external_url

logger = logging.getLogger(__name__)


def _dedupe_sources_by_key(sources: list[Source]) -> tuple[list[Source], int]:
    """Keep one Source row per source_key, preferring the newest id.

    The route already queries enabled sources, but this helper protects local
    databases that contain duplicate source rows from older development runs.
    """
    selected: dict[str, Source] = {}
    duplicate_count = 0

    for source in sources:
        existing = selected.get(source.source_key)
        if existing is None:
            selected[source.source_key] = source
            continue

        duplicate_count += 1

        # Prefer the newest row when duplicate keys exist.
        if source.id > existing.id:
            selected[source.source_key] = source

    return list(selected.values()), duplicate_count


def _get_radar_update_max_due_sources() -> int:
    """Return the cap on due sources enqueued per update click.

    Reads from RADAR_UPDATE_MAX_DUE_SOURCES env var.
    Default 30. 0 means no due source will be started this cycle.
    Falls back to 30 if invalid or out of [0, 500].
    """
    raw = os.getenv("RADAR_UPDATE_MAX_DUE_SOURCES")
    if raw is None:
        return 30
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 30
    if value < 0 or value > 500:
        return 30
    return value


def _build_due_source_reason_summary(plan: DueSourcePlan) -> str:
    """Build a compact reason summary string for the redirect query param."""
    counter: Counter[str] = Counter()
    for bucket in (plan.skipped, plan.running, plan.unsupported, plan.missing):
        for decision in bucket:
            counter[decision.reason] += 1
    return ",".join(f"{reason}:{count}" for reason, count in counter.most_common())


def _build_bootstrap_result(
    *,
    dry_run: int | None,
    total: int | None,
    eligible: int | None,
    started: int | None,
    skipped: int | None,
    unsupported: int | None,
    failed: int | None,
    message: str | None,
    execution_mode: str | None = None,
) -> dict | None:
    if not any(
        v is not None
        for v in (dry_run, total, eligible, started, skipped, unsupported, failed, message, execution_mode)
    ):
        return None
    return {
        "dry_run": bool(dry_run),
        "total": total or 0,
        "eligible": eligible or 0,
        "started": started or 0,
        "skipped": skipped or 0,
        "unsupported": unsupported or 0,
        "failed": failed or 0,
        "message": message or "",
        "execution_mode": execution_mode or "dry_run",
    }


# Mapping from internal reason keys to user-facing Chinese descriptions.
_REASON_LABEL: dict[str, str] = {
    "not_due_yet": "来源仍在冷却中",
    "max_sources_limit": "达到本轮检查上限",
    "already_running": "正在运行中",
    "missing_source_row": "来源记录缺失",
    "unsupported_fetch_strategy": "暂不支持的抓取方式",
}


def _humanize_reason_summary(raw: str | None) -> str | None:
    """Convert a raw due-source reason summary to user-facing Chinese.

    Examples:
      "not_due_yet:15"  -> "15 个来源仍在冷却中，暂不需要重复检查。"
      "not_due_yet:10,already_running:2" -> "10 个来源仍在冷却中，2 个正在运行中。"
      "" or None -> None
    """
    if not raw:
        return None
    parts: list[str] = []
    for segment in raw.split(","):
        segment = segment.strip()
        if not segment:
            continue
        if ":" in segment:
            reason, count_str = segment.rsplit(":", 1)
            try:
                count = int(count_str)
            except ValueError:
                parts.append(segment)
                continue
            label = _REASON_LABEL.get(reason, reason)
            parts.append(f"{count} 个{label}，暂不需要重复检查" if reason == "not_due_yet" else f"{count} 个{label}")
        else:
            parts.append(segment)
    if not parts:
        return None
    return "".join(parts) + "。"


def _parse_int_query(value: str | None, default: int = 0) -> int:
    """Safely parse an int query param; return default on failure."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_item_ids(raw: str | None, *, limit: int = 5) -> list[int]:
    """Parse a small comma-separated item-id list, preserving order."""
    if not raw:
        return []
    result: list[int] = []
    seen: set[int] = set()
    for part in raw.split(","):
        try:
            item_id = int(part.strip())
        except (TypeError, ValueError):
            continue
        if item_id <= 0 or item_id in seen:
            continue
        result.append(item_id)
        seen.add(item_id)
        if len(result) >= limit:
            break
    return result


def _build_insight_batch_status(raw_item_ids: str | None) -> dict | None:
    item_ids = _parse_item_ids(raw_item_ids)
    if not item_ids:
        return None

    db = next(get_db())
    try:
        rows = db.query(SourceItem).filter(SourceItem.id.in_(item_ids)).all()
        rows_by_id = {row.id: row for row in rows}
        details = []
        completed = running = failed = pending = 0
        retry_ids: list[int] = []
        for item_id in item_ids:
            item = rows_by_id.get(item_id)
            if item is None:
                status = "failed"
                status_label = "文章不存在"
                title = f"文章 #{item_id}"
                failed += 1
            elif item.status == "compiled" and item.insight_card_id:
                status = "completed"
                status_label = "洞察卡已生成"
                title = item.title or f"文章 #{item_id}"
                completed += 1
            elif item.status == "compiling":
                status = "running"
                status_label = "正在生成洞察卡"
                title = item.title or f"文章 #{item_id}"
                running += 1
            elif item.status == "failed":
                status = "failed"
                status_label = "生成失败，可重试"
                title = item.title or f"文章 #{item_id}"
                failed += 1
                retry_ids.append(item_id)
            else:
                status = "pending"
                status_label = "等待处理"
                title = item.title or f"文章 #{item_id}"
                pending += 1
            details.append({
                "item_id": item_id,
                "title": title,
                "status": status,
                "status_label": status_label,
                "error_label": (
                    _humanize_insight_error(item.error_message)
                    if item and status == "failed"
                    else ""
                ),
                "insight_card_id": item.insight_card_id if item else None,
            })
        return {
            "item_ids": item_ids,
            "details": details,
            "completed": completed,
            "running": running,
            "failed_actual": failed,
            "pending": pending,
            "retry_ids": retry_ids,
        }
    finally:
        db.close()


def _build_summary_batch_status(raw_item_ids: str | None) -> dict | None:
    from app.application.radar.background_summary import (
        SUMMARY_BATCH_ERROR_KEY,
        SUMMARY_BATCH_STATUS_KEY,
    )

    item_ids = _parse_item_ids(raw_item_ids, limit=50)
    if not item_ids:
        return None

    db = next(get_db())
    try:
        rows = db.query(SourceItem).filter(SourceItem.id.in_(item_ids)).all()
        rows_by_id = {row.id: row for row in rows}
        details = []
        completed = running = failed = pending = 0
        retry_ids: list[int] = []

        for item_id in item_ids:
            item = rows_by_id.get(item_id)
            title = item.title if item and item.title else f"文章 #{item_id}"
            raw = {}
            if item is not None:
                try:
                    raw = json.loads(item.raw_metadata_json or "{}")
                except (TypeError, json.JSONDecodeError):
                    raw = {}
                if not isinstance(raw, dict):
                    raw = {}

            # "Complete" = has both the one-liner and the detailed Chinese
            # summary, judged by the shared summary-state rule (single source of
            # truth) instead of re-deriving it here.
            _summary = summary_state_from_raw(raw)
            complete = _summary.has_one_liner and _summary.has_zh_summary
            batch_status = str(raw.get(SUMMARY_BATCH_STATUS_KEY) or "")
            error = str(raw.get(SUMMARY_BATCH_ERROR_KEY) or "")

            if item is None:
                status = "failed"
                status_label = "文章不存在"
                failed += 1
            elif complete:
                status = "completed"
                status_label = "中文摘要已完成"
                completed += 1
            elif batch_status == "running":
                status = "running"
                status_label = "正在生成中文摘要"
                running += 1
            elif batch_status == "failed":
                status = "failed"
                status_label = "生成失败，可重试"
                failed += 1
                retry_ids.append(item_id)
            else:
                status = "pending"
                status_label = "等待后台处理"
                pending += 1

            details.append({
                "item_id": item_id,
                "title": title,
                "status": status,
                "message_label": status_label,
                "error_label": error[:120] if status == "failed" else "",
            })

        return {
            "item_ids": item_ids,
            "details": details,
            "success": completed,
            "completed": completed,
            "running": running,
            "failed_actual": failed,
            "failed": failed,
            "pending": pending,
            "retry_ids": retry_ids,
        }
    finally:
        db.close()


router = APIRouter(prefix="/radar", tags=["radar"])


def _parse_summary_details(raw: str | None) -> list[dict[str, str]]:
    """Parse summary_details from redirect URL into a list of detail dicts."""
    if not raw:
        return []
    details = []
    for part in raw.split(";")[:5]:
        pieces = part.split(":", 2)
        if len(pieces) != 3:
            continue
        item_id, status, message = pieces
        details.append({
            "item_id": item_id,
            "status": status,
            "message": message,
            "message_label": _humanize_summary_detail_message(status, message),
        })
    return details


def _humanize_insight_error(message: str | None) -> str:
    raw = (message or "").lower()
    if "url is empty" in raw:
        return "缺少原文链接，暂时无法生成"
    if "[intake:blocked]" in raw:
        return "当前链接类型暂不支持自动深入分析"
    if "timeout" in raw:
        return "生成超时，可稍后重试"
    return "生成失败，可稍后重试"


def _humanize_summary_detail_message(status: str, message: str | None) -> str:
    """Convert a raw summary status + technical message to user-facing Chinese."""
    if status == "success":
        return "已生成中文摘要"
    elif status == "skipped":
        return "已有摘要，已跳过"
    elif status == "failed":
        return "中文摘要生成失败，可稍后重试"
    return "处理失败"

_radar_templates = Jinja2Templates(
    directory=Path(__file__).resolve().parent.parent / "templates",
    context_processors=[inject_sources_nav],
)


# ── Grouped action-result query params (PRG echo-back) ───────────────────────
# After a POST action redirects back to /radar/today, its result is carried in
# the URL query string. These dependency classes group those ~40 echo-back
# params so the GET signature stays small, and each knows how to assemble its
# own template-context dict. The URL contract is unchanged: FastAPI derives the
# same query params from each class __init__ as the old flat signature did.


class SummaryResultParams:
    """Echo-back params for the batch / single Chinese-summary result banner."""

    def __init__(
        self,
        summary_success: int | None = Query(None, ge=0),
        summary_skipped: int | None = Query(None, ge=0),
        summary_failed: int | None = Query(None, ge=0),
        summary_details: str | None = Query(None),
        summary_batch_ids: str | None = Query(None),
        summary_batch_accepted: int | None = Query(None, ge=0),
        summary_batch_skipped: int | None = Query(None, ge=0),
        summary_batch_failed: int | None = Query(None, ge=0),
    ):
        self.summary_success = summary_success
        self.summary_skipped = summary_skipped
        self.summary_failed = summary_failed
        self.summary_details = summary_details
        self.summary_batch_ids = summary_batch_ids
        self.summary_batch_accepted = summary_batch_accepted
        self.summary_batch_skipped = summary_batch_skipped
        self.summary_batch_failed = summary_batch_failed

    def build(self) -> dict | None:
        summary_result = _build_summary_batch_status(self.summary_batch_ids)
        if summary_result is not None:
            summary_result.update({
                "accepted": self.summary_batch_accepted or 0,
                "skipped": self.summary_batch_skipped or 0,
                "failed_enqueue": self.summary_batch_failed or 0,
                "background": True,
            })
        elif (
            self.summary_success is not None
            or self.summary_skipped is not None
            or self.summary_failed is not None
        ):
            summary_result = {
                "success": self.summary_success or 0,
                "skipped": self.summary_skipped or 0,
                "failed": self.summary_failed or 0,
                "details": _parse_summary_details(self.summary_details),
            }
            summary_result["retry_ids"] = [
                detail["item_id"]
                for detail in summary_result["details"]
                if detail["status"] == "failed" and detail["item_id"].isdigit()
            ]
        return summary_result


class InsightResultParams:
    """Echo-back params for the single-insight + batch-insight result banners."""

    def __init__(
        self,
        insight_status: str | None = Query(None),
        insight_message: str | None = Query(None),
        insight_batch_accepted: int | None = Query(None, ge=0),
        insight_batch_skipped: int | None = Query(None, ge=0),
        insight_batch_failed: int | None = Query(None, ge=0),
        insight_batch_ids: str | None = Query(None),
        insight_batch_total: int | None = Query(None, ge=0),
        insight_batch_hard_cap: int | None = Query(None, ge=0),
    ):
        self.insight_status = insight_status
        self.insight_message = insight_message
        self.insight_batch_accepted = insight_batch_accepted
        self.insight_batch_skipped = insight_batch_skipped
        self.insight_batch_failed = insight_batch_failed
        self.insight_batch_ids = insight_batch_ids
        self.insight_batch_total = insight_batch_total
        self.insight_batch_hard_cap = insight_batch_hard_cap

    def build_insight_result(self) -> dict | None:
        if self.insight_status is None:
            return None
        return {
            "status": self.insight_status,
            "message": self.insight_message or "",
        }

    def build_batch_result(self) -> dict | None:
        insight_batch_result = (
            {
                "accepted": self.insight_batch_accepted or 0,
                "skipped": self.insight_batch_skipped or 0,
                "failed": self.insight_batch_failed or 0,
                "total_candidates": self.insight_batch_total or 0,
                "hard_cap": self.insight_batch_hard_cap or 0,
            }
            if any(
                value is not None
                for value in (
                    self.insight_batch_accepted,
                    self.insight_batch_skipped,
                    self.insight_batch_failed,
                )
            )
            else None
        )
        insight_batch_status = _build_insight_batch_status(self.insight_batch_ids)
        if insight_batch_result and insight_batch_status:
            insight_batch_result.update(insight_batch_status)
        elif insight_batch_status:
            insight_batch_result = insight_batch_status
            insight_batch_result.update({"accepted": 0, "skipped": 0, "failed": 0})
        return insight_batch_result


class UpdateResultParams:
    """Echo-back params for the "同步今日新增" due-source result banner."""

    def __init__(
        self,
        update_started: int | None = Query(None, ge=0),
        update_running: int | None = Query(None, ge=0),
        update_unsupported: int | None = Query(None, ge=0),
        update_failed: int | None = Query(None, ge=0),
        update_truncated: int | None = Query(None, ge=0),
        update_unique_sources: int | None = Query(None, ge=0),
        update_duplicate_sources: int | None = Query(None, ge=0),
        update_configured_sources: int | None = Query(None, ge=0),
        update_filtered_sources: int | None = Query(None, ge=0),
        # New due-source summary fields (V1.0-beta.1)
        update_total: int | None = Query(None, ge=0),
        update_due: int | None = Query(None, ge=0),
        update_skipped: int | None = Query(None, ge=0),
        update_missing: int | None = Query(None, ge=0),
        update_reason_summary: str | None = Query(None),
        update_plan_source: str | None = Query(None),
    ):
        self.update_started = update_started
        self.update_running = update_running
        self.update_unsupported = update_unsupported
        self.update_failed = update_failed
        self.update_truncated = update_truncated
        self.update_unique_sources = update_unique_sources
        self.update_duplicate_sources = update_duplicate_sources
        self.update_configured_sources = update_configured_sources
        self.update_filtered_sources = update_filtered_sources
        self.update_total = update_total
        self.update_due = update_due
        self.update_skipped = update_skipped
        self.update_missing = update_missing
        self.update_reason_summary = update_reason_summary
        self.update_plan_source = update_plan_source

    def build(self) -> dict | None:
        if not any(v is not None for v in [
            self.update_started,
            self.update_running,
            self.update_unsupported,
            self.update_failed,
            self.update_truncated,
            self.update_unique_sources,
            self.update_duplicate_sources,
            self.update_configured_sources,
            self.update_filtered_sources,
            self.update_total,
            self.update_due,
            self.update_skipped,
            self.update_missing,
            self.update_reason_summary,
            self.update_plan_source,
        ]):
            return None
        return {
            "started": self.update_started or 0,
            "running": self.update_running or 0,
            "unsupported": self.update_unsupported or 0,
            "failed": self.update_failed or 0,
            "truncated": self.update_truncated or 0,
            "unique_sources": self.update_unique_sources or 0,
            "duplicate_sources": self.update_duplicate_sources or 0,
            "configured_sources": self.update_configured_sources or 0,
            "filtered_sources": self.update_filtered_sources or 0,
            # New due-source summary fields (V1.0-beta.1)
            "total": self.update_total or 0,
            "due": self.update_due or 0,
            "skipped": self.update_skipped or 0,
            "missing": self.update_missing or 0,
            "reason_summary": self.update_reason_summary or "",
            "reason_summary_label": _humanize_reason_summary(self.update_reason_summary) or "",
            "plan_source": self.update_plan_source or "",
        }


class BootstrapResultParams:
    """Echo-back params for the "初始化来源内容" bootstrap result banner."""

    def __init__(
        self,
        bootstrap_dry_run: int | None = Query(None, ge=0),
        bootstrap_total: int | None = Query(None, ge=0),
        bootstrap_eligible: int | None = Query(None, ge=0),
        bootstrap_started: int | None = Query(None, ge=0),
        bootstrap_skipped: int | None = Query(None, ge=0),
        bootstrap_unsupported: int | None = Query(None, ge=0),
        bootstrap_failed: int | None = Query(None, ge=0),
        bootstrap_message: str | None = Query(None),
        bootstrap_execution_mode: str | None = Query(None),
    ):
        self.bootstrap_dry_run = bootstrap_dry_run
        self.bootstrap_total = bootstrap_total
        self.bootstrap_eligible = bootstrap_eligible
        self.bootstrap_started = bootstrap_started
        self.bootstrap_skipped = bootstrap_skipped
        self.bootstrap_unsupported = bootstrap_unsupported
        self.bootstrap_failed = bootstrap_failed
        self.bootstrap_message = bootstrap_message
        self.bootstrap_execution_mode = bootstrap_execution_mode

    def build(self) -> dict | None:
        return _build_bootstrap_result(
            dry_run=self.bootstrap_dry_run,
            total=self.bootstrap_total,
            eligible=self.bootstrap_eligible,
            started=self.bootstrap_started,
            skipped=self.bootstrap_skipped,
            unsupported=self.bootstrap_unsupported,
            failed=self.bootstrap_failed,
            message=self.bootstrap_message,
            execution_mode=self.bootstrap_execution_mode,
        )


class ResumeResultParams:
    """Echo-back params for the interrupted-batch resume confirmation (P4)."""

    def __init__(
        self,
        resumed_summary: int | None = Query(None, ge=0),
        resumed_insight: int | None = Query(None, ge=0),
    ):
        self.resumed_summary = resumed_summary
        self.resumed_insight = resumed_insight

    def build(self) -> dict | None:
        if self.resumed_summary is None and self.resumed_insight is None:
            return None
        summary = self.resumed_summary or 0
        insight = self.resumed_insight or 0
        return {"summary": summary, "insight": insight, "total": summary + insight}


@router.get("/today", response_class=HTMLResponse)
def radar_today_page(
    request: Request,
    item_id: int | None = Query(None),
    hours: int = Query(DEFAULT_HOURS, ge=MIN_HOURS, le=MAX_HOURS),
    limit: int = Query(DEFAULT_LIMIT, ge=MIN_LIMIT, le=MAX_LIMIT),
    page: int = Query(1, ge=1),
    per_page: int = Query(DEFAULT_PER_PAGE, ge=MIN_PER_PAGE, le=MAX_PER_PAGE),
    section: str = Query("auto"),
    panel: str | None = Query(None),
    summary_params: SummaryResultParams = Depends(),
    insight_params: InsightResultParams = Depends(),
    update_params: UpdateResultParams = Depends(),
    bootstrap_params: BootstrapResultParams = Depends(),
    resume_params: ResumeResultParams = Depends(),
):
    """Render today's AI frontier radar reading view."""
    # Build base context using shared helper
    context = _build_radar_today_view_context(
        request=request,
        item_id=item_id,
        hours=hours,
        limit=limit,
        page=page,
        per_page=per_page,
        section=section,
    )

    context["summary_result"] = summary_params.build()
    context["insight_result"] = insight_params.build_insight_result()
    context["insight_batch_result"] = insight_params.build_batch_result()
    context["update_result"] = update_params.build()
    context["bootstrap_result"] = bootstrap_params.build()
    context["resume_result"] = resume_params.build()
    context["panel_mode"] = panel

    return _radar_templates.TemplateResponse(
        "radar_today.html",
        context,
    )


@router.post("/today/daily-report", response_class=HTMLResponse)
def generate_daily_core_report(
    request: Request,
    force: bool = Form(False),
):
    """Explicitly generate today's core report (P-003-2).

    POST only — side-effecting (may call the LLM). Gated: the LLM is only
    reached when ``DAILY_REPORT_ENABLED=true``; otherwise the result is
    ``status="disabled"`` and no LLM call happens. Successful results are
    persisted as runtime JSON so they remain available after refresh.
    """
    from app.db import get_db
    from app.application.radar.daily_report import (
        build_daily_report_input,
        daily_report_input_fingerprint,
        generate_daily_report,
    )
    from app.application.radar.daily_report_store import (
        load_daily_report,
        save_daily_report,
    )

    db = next(get_db())
    try:
        try:
            payload = build_daily_report_input(db)
            fingerprint = daily_report_input_fingerprint(payload)
            existing = load_daily_report(payload.date_label)
            if (
                not force
                and existing is not None
                and existing.get("input_fingerprint") == fingerprint
            ):
                daily_report_result = existing
                daily_report_result["message"] = "今日内容未变化，已复用现有核心报告。"
            else:
                report = generate_daily_report(db, apply=True)
                daily_report_result = {
                    "status": report.status,
                    "date_label": report.date_label,
                    "input_item_count": report.input_item_count,
                    "input_fingerprint": report.input_fingerprint,
                    "message": report.message,
                    "title": report.title,
                    "overview": report.overview,
                    "highlights": report.highlights,
                    "highlight_references": report.highlight_references,
                }
                if report.status == "generated":
                    stored_result = save_daily_report(report)
                    if stored_result is not None:
                        daily_report_result = stored_result
        except Exception:
            daily_report_result = {
                "status": "error",
                "message": "今日核心报告生成失败，请稍后重试。",
                "highlights": [],
                "highlight_references": [],
            }

        context = _build_daily_report_page_context(
            request,
            daily_report_result=daily_report_result,
        )
        return _radar_templates.TemplateResponse("radar_daily_report.html", context)
    finally:
        db.close()


@router.post("/today/audio")
def generate_today_audio(
    background_tasks: BackgroundTasks,
    report_version: str | None = Form(None),
):
    """Generate or reuse the current report's default audio narration."""
    from app.application.radar.daily_audio_jobs import (
        enqueue_daily_audio_job,
        run_daily_audio_job,
    )
    from app.application.radar.mimo_tts import MiMoTTSSettings

    try:
        settings = MiMoTTSSettings.from_env()
        script, script_basis, resolved_version = _build_daily_broadcast_page_data(
            report_version,
        )
        result = enqueue_daily_audio_job(
            script,
            script_basis=script_basis,
            voice=settings.voice,
            style=settings.style,
            report_version=resolved_version,
        )
    except Exception as exc:
        return RedirectResponse(
            url="/radar/daily-report/broadcast?"
            + urlencode({"audio_error": str(exc)[:300]}),
            status_code=303,
        )

    if result.should_start:
        background_tasks.add_task(run_daily_audio_job, result.job.job_id)
    return RedirectResponse(
        url="/radar/today#today-summary",
        status_code=303,
    )


def _build_radar_today_view_context(
    request: Request,
    item_id: int | None,
    hours: int,
    limit: int,
    page: int,
    per_page: int,
    section: str,
    include_sidebar: bool = True,
):
    """Build the context dict for radar today view (shared by full page and panel).

    ``include_sidebar`` controls the left-sidebar-only aggregates (scheduler
    status + daily digest). The right reading panel does not use them, so the
    panel partial route passes ``include_sidebar=False`` to skip that work
    (avoids a due-source N+1 + several digest counts on every panel refresh).
    """
    db = next(get_db())
    try:
        configured_sources = [s for s in list_sources() if s.enabled]
        configured_keys = {s.source_key for s in configured_sources}

        service = RadarTodayService(db)
        view = service.build_today_view(
            selected_item_id=item_id,
            hours=hours,
            limit=limit,
            page=page,
            per_page=per_page,
            section=section,
            fetch_run_source_keys=configured_keys,
        )

        # Left-sidebar-only aggregates — skipped for the panel partial refresh.
        scheduler_status = None
        daily_digest = None
        today_summary_panel = None
        if include_sidebar:
            # V1.0-beta.3: read-only scheduler status for the sidebar block.
            try:
                from app.application.radar.status_view import (
                    build_radar_scheduler_status_view,
                )
                scheduler_status = build_radar_scheduler_status_view(db)
            except Exception:
                scheduler_status = None

            # P-003 step 1: read-only daily digest (no LLM). Degrades gracefully.
            try:
                from app.application.radar.daily_digest import build_daily_digest_view
                daily_digest = build_daily_digest_view(db)
            except Exception:
                daily_digest = None

            # Today summary panel: core report + latest audio for the sidebar module.
            try:
                from app.application.radar.daily_report import (
                    build_daily_report_input,
                    daily_report_input_fingerprint,
                )
                from app.application.radar.today_summary_panel import (
                    build_today_summary_panel_view,
                )
                report_input = build_daily_report_input(db)
                today_summary_panel = build_today_summary_panel_view(
                    date_label=(
                        daily_digest.date_label
                        if daily_digest is not None
                        else None
                    ),
                    current_input_fingerprint=daily_report_input_fingerprint(
                        report_input
                    ),
                )
            except Exception:
                logger.exception("Unable to build today summary panel")
                today_summary_panel = None

        # P4: interrupted background batches (summary/insight left in-progress by
        # a process restart). Read-only count for the recovery banner.
        interrupted_batches = None
        if include_sidebar:
            try:
                from app.application.radar.batch_recovery import (
                    count_interrupted_batches,
                )
                interrupted_batches = count_interrupted_batches(db)
            except Exception:
                interrupted_batches = None

        sel = view.selected_item
        sel_card = view.display_map.get(sel.id) if sel else None

        return {
            "request": request,
            "view": view,
            "display_map": view.display_map,
            "today_card_map": view.today_card_map,
            "safe_external_url": safe_external_url,
            "scheduler_status": scheduler_status,
            "daily_digest": daily_digest,
            "today_summary_panel": today_summary_panel,
            "interrupted_batches": interrupted_batches,
            "sel": sel,
            "sel_card": sel_card,
            "DAILY_REPORT_ENABLED": get_daily_report_enabled(),
            "SUMMARY_BATCH_LIMIT": SUMMARY_BATCH_LIMIT,
            "RECOMMENDED_INSIGHT_LIMIT": RECOMMENDED_INSIGHT_LIMIT,
            "RECOMMENDED_INSIGHT_HARD_CAP": RECOMMENDED_INSIGHT_HARD_CAP,
        }
    finally:
        db.close()


@router.get("/today/briefing", response_class=HTMLResponse)
def radar_today_briefing(request: Request):
    """Read-only "今日新增简报": today's newly discovered items grouped by source.

    The deterministic new-items report — lists everything new today with its
    Chinese one-liner (or title), discovery time, and read links. No LLM, no
    writes, and does not touch the today-radar reading layout.
    """
    db = next(get_db())
    try:
        from app.application.radar.daily_digest import build_daily_briefing
        briefing = build_daily_briefing(db)
        return _radar_templates.TemplateResponse(
            "radar_briefing.html",
            {
                "request": request,
                "briefing": briefing,
                "safe_external_url": safe_external_url,
            },
        )
    finally:
        db.close()


@router.get("/today/panel")
def radar_today_panel(
    request: Request,
    item_id: int | None = Query(None),
    hours: int = Query(DEFAULT_HOURS, ge=MIN_HOURS, le=MAX_HOURS),
    limit: int = Query(DEFAULT_LIMIT, ge=MIN_LIMIT, le=MAX_LIMIT),
    page: int = Query(1, ge=1),
    per_page: int = Query(DEFAULT_PER_PAGE, ge=MIN_PER_PAGE, le=MAX_PER_PAGE),
    section: str = Query(ALL_KEY),
    panel: str | None = Query(None),
):
    """Return only the right-panel HTML fragment for partial fetch updates."""
    context = _build_radar_today_view_context(
        request=request,
        item_id=item_id,
        hours=hours,
        limit=limit,
        page=page,
        per_page=per_page,
        section=section,
        include_sidebar=False,  # panel partial uses neither scheduler_status nor daily_digest
    )
    context["panel_mode"] = panel
    context["RECOMMENDED_INSIGHT_LIMIT"] = RECOMMENDED_INSIGHT_LIMIT
    context["RECOMMENDED_INSIGHT_HARD_CAP"] = RECOMMENDED_INSIGHT_HARD_CAP
    return _radar_templates.TemplateResponse(
        "partials/radar_today_panel.html",
        context,
    )


@router.post("/today/items/{item_id}/fetch-html")
def fetch_today_item_html(
    item_id: int,
    section: str = Form(ALL_KEY),
    hours: int = Form(DEFAULT_HOURS),
    limit: int = Form(DEFAULT_LIMIT),
    page: int = Form(1),
    per_page: int = Form(DEFAULT_PER_PAGE),
):
    """Fetch HTML content for a radar item and save a snapshot.

    This route performs a synchronous HTML fetch and saves a text snapshot.
    It does NOT call any LLM. Network failures are handled gracefully.
    """
    from app.application.content.source_item_content_service import (
        fetch_source_item_content,
        ContentFetchStatus,
    )

    db = next(get_db())
    try:
        result = fetch_source_item_content(db, item_id, force=True)

        # Build status message for redirect
        if result.status == ContentFetchStatus.FETCHED:
            msg = "html_fetch_success"
        elif result.status == ContentFetchStatus.FAILED:
            msg = f"html_fetch_failed:{result.error or 'unknown'}"
        elif result.status == ContentFetchStatus.SKIPPED:
            msg = f"html_fetch_skipped:{result.error or 'unknown'}"
        elif result.status == "not_found":
            msg = "html_fetch_not_found"
        else:
            msg = f"html_fetch_{result.status}"

        params = {
            "section": section,
            "item_id": item_id,
            "hours": hours,
            "limit": limit,
            "page": page,
            "per_page": per_page,
            "html_fetch_status": result.status,
            "html_fetch_message": msg,
        }
        return RedirectResponse(url="/radar/today?" + urlencode(params), status_code=303)
    finally:
        db.close()


@router.post("/today/items/{item_id}/generate-summary")
def generate_today_item_summary(
    item_id: int,
    section: str = Form(ALL_KEY),
    hours: int = Form(DEFAULT_HOURS),
    limit: int = Form(DEFAULT_LIMIT),
    page: int = Form(1),
    per_page: int = Form(DEFAULT_PER_PAGE),
):
    """Generate a summary from content snapshot for a radar item.

    This route generates a Chinese summary from the HTML content snapshot.
    It requires LLM_SUMMARY_ENABLED=true and proper LLM configuration.
    Returns redirect to the radar page with status message.
    """
    from app.application.summary.source_item_summary_service import (
        generate_source_item_summary,
        SummaryStatus,
    )

    db = next(get_db())
    try:
        result = generate_source_item_summary(db, item_id, force=False)

        # Build status message for redirect
        if result.status == SummaryStatus.GENERATED:
            msg = "summary_generated"
        elif result.status == SummaryStatus.SKIPPED:
            msg = "summary_skipped:already_generated"
        elif result.status == SummaryStatus.DISABLED:
            msg = "summary_disabled:llm_not_configured"
        elif result.status == SummaryStatus.MISSING_SNAPSHOT:
            msg = "summary_failed:missing_snapshot"
        elif result.status == SummaryStatus.FAILED:
            msg = f"summary_failed:{result.error or 'unknown'}"
        elif result.status == SummaryStatus.NOT_ELIGIBLE:
            msg = "summary_skipped:not_eligible"
        else:
            msg = f"summary_{result.status}"

        params = {
            "section": section,
            "item_id": item_id,
            "hours": hours,
            "limit": limit,
            "page": page,
            "per_page": per_page,
            "summary_status": result.status,
            "summary_message": msg,
        }
        return RedirectResponse(url="/radar/today?" + urlencode(params), status_code=303)
    finally:
        db.close()


@router.post("/today/items/{item_id}/generate-insight")
def generate_today_item_insight(
    item_id: int,
    section: str = Form(ALL_KEY),
    hours: int = Form(DEFAULT_HOURS),
    limit: int = Form(DEFAULT_LIMIT),
    page: int = Form(1),
    per_page: int = Form(DEFAULT_PER_PAGE),
):
    """Generate an InsightCard from content summary for a radar item.

    This route generates an InsightCard from the existing summary_json.
    It does NOT call any LLM. Returns redirect to the radar page.
    """
    from app.application.insight.source_item_insight_service import generate_source_item_insight
    from app.application.insight.insight_models import InsightStatus

    db = next(get_db())
    try:
        result = generate_source_item_insight(db, item_id, force=False)

        # Build status message for redirect
        if result.status == InsightStatus.GENERATED:
            msg = "insight_generated"
        elif result.status == "updated":
            msg = "insight_updated"
        elif result.status == InsightStatus.SKIPPED:
            msg = "insight_skipped:already_exists"
        elif result.status == InsightStatus.NOT_ELIGIBLE:
            msg = f"insight_not_eligible:{result.error or 'no_summary'}"
        else:
            msg = f"insight_{result.status}"

        params = {
            "section": section,
            "item_id": item_id,
            "hours": hours,
            "limit": limit,
            "page": page,
            "per_page": per_page,
            "insight_status": result.status,
            "insight_message": msg,
        }
        return RedirectResponse(url="/radar/today?" + urlencode(params), status_code=303)
    finally:
        db.close()


@router.post("/today/generate-summaries")
def generate_today_summaries(
    background_tasks: BackgroundTasks,
    section: str = Form(ALL_KEY),
    item_id: int | None = Form(None),
    hours: int = Form(DEFAULT_HOURS),
    limit: int = Form(DEFAULT_LIMIT),
    page: int = Form(1),
    per_page: int = Form(DEFAULT_PER_PAGE),
    summary_limit: int = Form(SUMMARY_BATCH_LIMIT),
    summary_item_ids: str | None = Form(None),
):
    """Queue Chinese-summary generation for up to 50 today-radar items."""
    from app.application.radar.background_summary import (
        enqueue_summary_batch,
        run_summary_batch_in_background,
    )

    db = next(get_db())
    try:
        # Only the ordered batch-target ids are needed (recommended first, then
        # today's items in section order). Compute them directly instead of
        # building the whole today-view (reading panel, today-cards, quality-stats
        # full scan). The ordering is identical to the old derivation.
        target_ids = RadarTodayService(db).build_summary_target_ids(
            hours=hours,
            limit=limit,
            per_page=MAX_PER_PAGE,
        )

        requested_ids = _parse_item_ids(
            summary_item_ids,
            limit=SUMMARY_BATCH_LIMIT,
        )
        if requested_ids:
            allowed_ids = set(target_ids)
            target_ids = [
                requested_id
                for requested_id in requested_ids
                if requested_id in allowed_ids
            ]

        max_items = max(1, min(summary_limit, SUMMARY_BATCH_LIMIT))
        target_ids = target_ids[:max_items]
    finally:
        db.close()

    enqueue_result = enqueue_summary_batch(
        target_ids,
        hard_cap=SUMMARY_BATCH_LIMIT,
    )
    if enqueue_result.accepted_ids:
        background_tasks.add_task(
            run_summary_batch_in_background,
            enqueue_result.accepted_ids,
        )

    params = {
        "section": section,
        "hours": hours,
        "limit": limit,
        "page": page,
        "per_page": per_page,
        "summary_batch_ids": ",".join(
            str(target_id) for target_id in enqueue_result.tracked_ids
        ),
        "summary_batch_accepted": len(enqueue_result.accepted_ids),
        "summary_batch_skipped": enqueue_result.skipped,
        "summary_batch_failed": enqueue_result.failed,
    }
    if item_id is not None:
        params["item_id"] = item_id
    return RedirectResponse(
        url="/radar/today?" + urlencode(params),
        status_code=303,
    )


@router.post("/today/generate-recommended-insights")
def generate_recommended_insights(
    background_tasks: BackgroundTasks,
    section: str = Form(ALL_KEY),
    hours: int = Form(DEFAULT_HOURS),
    limit: int = Form(DEFAULT_LIMIT),
    page: int = Form(1),
    per_page: int = Form(DEFAULT_PER_PAGE),
    insight_limit: int | None = Form(None),
    insight_item_ids: str | None = Form(None),
):
    """Enqueue the top recommended items for InsightCard generation."""
    from app.application.source_items.background_compile import (
        BackgroundCompileService,
        run_source_item_compile_in_background,
    )

    db = next(get_db())
    try:
        # Only the recommended candidate ids are needed here, so compute just
        # those instead of building the whole today-view (display cards, sections,
        # panel, stats). The candidate set is identical to view.compile_candidates.
        candidates = RadarTodayService(db).select_recommended_candidates(
            hours=hours,
            limit=limit,
        )
        all_candidate_ids = [c.source_item_id for c in candidates]

        # Specific item IDs override limit (retry flow)
        if insight_item_ids:
            requested_ids = _parse_item_ids(insight_item_ids, limit=9999)
            allowed_ids = set(all_candidate_ids)
            base_ids = [iid for iid in requested_ids if iid in allowed_ids]
        elif insight_limit is not None:
            base_ids = all_candidate_ids[:max(1, int(insight_limit))]
        else:
            base_ids = all_candidate_ids  # None = all candidates

        # Apply hard-cap safety ceiling
        total_candidates = len(all_candidate_ids)
        target_ids = base_ids[:RECOMMENDED_INSIGHT_HARD_CAP]
        hard_cap_triggered = total_candidates > RECOMMENDED_INSIGHT_HARD_CAP
    finally:
        db.close()

    accepted = 0
    skipped = 0
    failed = 0
    tracked_ids: list[int] = []
    enqueue_service = BackgroundCompileService()
    for target_id in target_ids:
        tracked_ids.append(target_id)
        try:
            result = enqueue_service.enqueue_item(target_id)
        except Exception:
            failed += 1
            continue
        if result.accepted:
            accepted += 1
            background_tasks.add_task(
                run_source_item_compile_in_background,
                target_id,
            )
        elif result.status in {"compiled", "compiling"}:
            skipped += 1
        else:
            failed += 1

    params = {
        "section": section,
        "hours": hours,
        "limit": limit,
        "page": page,
        "per_page": per_page,
        "panel": "recommendations",
        "insight_batch_accepted": accepted,
        "insight_batch_skipped": skipped,
        "insight_batch_failed": failed,
        "insight_batch_ids": ",".join(str(item_id) for item_id in tracked_ids),
        "insight_batch_total": total_candidates,
        "insight_batch_hard_cap": RECOMMENDED_INSIGHT_HARD_CAP if hard_cap_triggered else 0,
    }
    return RedirectResponse(url="/radar/today?" + urlencode(params), status_code=303)


@router.post("/today/resume-interrupted")
def resume_interrupted_today_batches(
    background_tasks: BackgroundTasks,
    section: str = Form(ALL_KEY),
    item_id: int | None = Form(None),
    hours: int = Form(DEFAULT_HOURS),
    limit: int = Form(DEFAULT_LIMIT),
    page: int = Form(1),
    per_page: int = Form(DEFAULT_PER_PAGE),
):
    """Re-run background batches (summary/insight) interrupted by a restart (P4).

    Detection is read-only; re-running dispatches to the same background runners
    the original enqueue paths use. Does not call the LLM directly.
    """
    from app.application.radar.batch_recovery import resume_interrupted_batches

    result = resume_interrupted_batches(background_tasks)

    params = {
        "section": normalize_section_key(section),
        "hours": hours,
        "limit": limit,
        "page": page,
        "per_page": per_page,
        "resumed_summary": result.summary,
        "resumed_insight": result.insight,
    }
    if item_id is not None:
        params["item_id"] = item_id
    return RedirectResponse(url="/radar/today?" + urlencode(params), status_code=303)


@router.post("/today/bootstrap")
def bootstrap_today_sources(
    background_tasks: BackgroundTasks,
    section: str = Form(ALL_KEY),
    item_id: int | None = Form(None),
    hours: int = Form(DEFAULT_HOURS),
    limit: int = Form(DEFAULT_LIMIT),
    page: int = Form(1),
    per_page: int = Form(DEFAULT_PER_PAGE),
    max_items_per_source: int = Form(20),
    max_sources: int = Form(15),
    action: str = Form("dry_run"),
):
    """Plan or run bootstrap discovery for enabled YAML sources.

    GET is intentionally not defined. Dry-run is the default; apply requires a
    form value of action=apply. The underlying discovery service disables
    fetch-run auto summaries during apply, so this route does not call LLMs.

    Apply mode runs in the background via FastAPI BackgroundTasks to avoid
    blocking the HTTP request. CLI apply uses synchronous execution instead.
    """
    dry_run = action != "apply"
    db = next(get_db())
    try:
        result = run_source_discovery(
            db,
            SourceDiscoveryRunSettings(
                mode=BOOTSTRAP_MODE,
                max_items_per_source=max_items_per_source,
                max_sources=max_sources,
                dry_run=dry_run,
            ),
            background_tasks=background_tasks if not dry_run else None,
        )
    finally:
        db.close()

    params = {
        "section": section,
        "hours": hours,
        "limit": limit,
        "page": page,
        "per_page": per_page,
        "bootstrap_dry_run": 1 if result.dry_run else 0,
        "bootstrap_total": result.total_sources,
        "bootstrap_eligible": result.eligible_sources,
        "bootstrap_started": result.started,
        "bootstrap_skipped": result.skipped,
        "bootstrap_unsupported": result.unsupported,
        "bootstrap_failed": result.failed,
        "bootstrap_message": result.message,
        "bootstrap_execution_mode": result.execution_mode,
    }
    if item_id is not None:
        params["item_id"] = item_id
    return RedirectResponse(url="/radar/today?" + urlencode(params), status_code=303)


@router.post("/today/update")
def update_today_radar(
    background_tasks: BackgroundTasks,
    section: str = Form(ALL_KEY),
    item_id: int | None = Form(None),
    hours: int = Form(DEFAULT_HOURS),
    limit: int = Form(DEFAULT_LIMIT),
    page: int = Form(1),
    per_page: int = Form(DEFAULT_PER_PAGE),
):
    """Compute due-source plan and enqueue only due sources.

    V1.0-beta.1: enqueues only sources whose due-source plan status is "due".
    Sources in skipped / running / unsupported / missing buckets are NOT enqueued.
    """
    max_due_sources = _get_radar_update_max_due_sources()

    # Compute the due-source plan (read-only).
    db = next(get_db())
    try:
        plan = compute_due_sources(db, max_sources=max_due_sources)
    finally:
        db.close()

    # Enqueue only plan.due — single failure does not affect the rest.
    fetch_service = SourceFetchBackgroundService()
    started = 0
    failed = 0

    for decision in plan.due:
        try:
            result = fetch_service.enqueue_source(
                decision.source_key,
                background_tasks=background_tasks,
            )
        except Exception:
            failed += 1
            continue

        if getattr(result, "accepted", False) and getattr(result, "status", "") in ("running", "queued"):
            started += 1
        else:
            failed += 1

    # The redirect only needs the validated section. active_section is a pure
    # function of the input string, so normalize it directly instead of building
    # a full today-view (which would also run a 300-item candidate scan here).
    safe_section = normalize_section_key(section)

    reason_summary = _build_due_source_reason_summary(plan)

    # Redirect back to /radar/today with result stats.
    # Both legacy and new due-source fields are carried so the template can
    # render either style.
    redirect_url = (
        f"/radar/today?section={safe_section}"
        f"&hours={hours}&limit={limit}&page={page}&per_page={per_page}"
    )
    if item_id is not None:
        redirect_url += f"&item_id={item_id}"

    # New due-source summary fields
    redirect_url += (
        f"&update_total={plan.total_configured}"
        f"&update_due={plan.due_count}"
        f"&update_started={started}"
        f"&update_skipped={plan.skipped_count}"
        f"&update_running={plan.running_count}"
        f"&update_unsupported={plan.unsupported_count}"
        f"&update_missing={plan.missing_count}"
        f"&update_failed={failed}"
        f"&update_plan_source=due_sources_v1"
    )
    if reason_summary:
        redirect_url += f"&update_reason_summary={reason_summary}"

    # Legacy compatibility fields (still computed for backwards compatibility)
    redirect_url += (
        f"&update_unique_sources={plan.total_configured}"
        f"&update_duplicate_sources=0"
        f"&update_configured_sources={plan.total_configured}"
        f"&update_filtered_sources=0"
        f"&update_truncated={max(0, plan.due_count - started)}"
    )
    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/history", response_class=HTMLResponse)
def radar_history(request: Request):
    """Per-day history index (P5): past days that have a persisted report."""
    from app.application.radar.history import list_history_days

    db = next(get_db())
    try:
        days = list_history_days(db)
    finally:
        db.close()
    return _radar_templates.TemplateResponse(
        "radar_history.html", {"request": request, "days": days}
    )


@router.get("/history/{date_label}", response_class=HTMLResponse)
def radar_history_day(request: Request, date_label: str):
    """Read-only detail for one past day: its report, audio, and articles."""
    import re as _re
    from app.application.radar.history import build_history_day_view

    if not _re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_label):
        return HTMLResponse("无效日期。", status_code=400)

    db = next(get_db())
    try:
        view = build_history_day_view(db, date_label)
    finally:
        db.close()
    return _radar_templates.TemplateResponse(
        "radar_history_day.html",
        {"request": request, "view": view, "safe_external_url": safe_external_url},
    )


def _render_share(request: Request, date_label: str):
    from app.application.radar.share import build_share_view, build_qr_svg
    from app.application.radar.share_video import video_enabled

    db = next(get_db())
    try:
        view = build_share_view(db, date_label)
    finally:
        db.close()
    share_url = str(request.url)
    try:
        qr_svg = build_qr_svg(share_url)
    except Exception:
        qr_svg = None  # never let QR generation break the page
    return _radar_templates.TemplateResponse(
        "radar_share.html",
        {
            "request": request,
            "view": view,
            "safe_external_url": safe_external_url,
            "share_url": share_url,
            "qr_svg": qr_svg,
            "video_enabled": bool(view.audio_job) and video_enabled(),
        },
    )


@router.post("/share/{date_label}/video")
async def radar_share_video(
    date_label: str,
    cover: UploadFile = File(...),
    lines: str = Form("[]"),
):
    """Deprecated legacy html2canvas audiogram route.

    Kept only for backward compatibility.
    New video generation uses POST /share/{date_label}/video/generate
    (structured-content → 9:16 MP4 via Pillow scenes + TTS).
    """
    import re as _re
    import re as _re
    import json as _json
    from app.application.radar.share import build_share_view
    from app.application.radar.share_video import compose_audiogram, resolve_ffmpeg
    from app.application.radar.daily_broadcast import get_daily_broadcast_audio_path

    if not _re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_label):
        return Response("无效日期。", status_code=400)
    if resolve_ffmpeg() is None:
        return Response("服务器未安装 ffmpeg，无法生成视频。", status_code=503)

    db = next(get_db())
    try:
        view = build_share_view(db, date_label)
    finally:
        db.close()
    job = view.audio_job
    if not job or not job.audio_filename:
        return Response("当日无可用音频。", status_code=400)
    audio_path = get_daily_broadcast_audio_path(job.audio_filename)
    if not audio_path or not audio_path.is_file():
        return Response("音频文件不存在。", status_code=400)

    cover_bytes = await cover.read()
    if not cover_bytes:
        return Response("封面图为空。", status_code=400)
    try:
        parsed_lines = _json.loads(lines) if lines else []
        if not isinstance(parsed_lines, list):
            parsed_lines = []
    except (ValueError, TypeError):
        parsed_lines = []
    try:
        mp4 = compose_audiogram(cover_bytes, audio_path, lines=parsed_lines)
    except Exception as exc:
        return Response(f"视频生成失败：{exc}", status_code=500)

    filename = f"AI_Frontier_Radar_{date_label}.mp4"
    return Response(
        content=mp4,
        media_type="video/mp4",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/share", response_class=HTMLResponse)
def radar_share_history(request: Request):
    """Index of formal daily reports linking to their public share pages."""
    from app.application.radar.history import list_history_days

    db = next(get_db())
    try:
        days = list_history_days(db)
    finally:
        db.close()
    return _radar_templates.TemplateResponse(
        "radar_share_history.html",
        {"request": request, "days": days},
    )


@router.get("/share/today", response_class=HTMLResponse)
def radar_share_today(request: Request):
    """Public share page for the most recent formal daily report."""
    from app.application.radar.daily_report_store import (
        list_daily_report_dates,
        list_final_daily_report_dates,
    )
    from app.application.radar.daily_scope import latest_completed_date_label

    dates = list_final_daily_report_dates() or list_daily_report_dates()
    return _render_share(
        request,
        dates[0] if dates else latest_completed_date_label(),
    )


@router.get("/share/{date_label}", response_class=HTMLResponse)
def radar_share_day(request: Request, date_label: str):
    """Public read-only share page (H5) for a given day."""
    import re as _re

    if not _re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_label):
        return HTMLResponse("无效日期。", status_code=400)
    return _render_share(request, date_label)


@router.get("/daily-report", response_class=HTMLResponse)
def get_daily_report_card(
    request: Request,
    version: str | None = Query(None),
):
    """Render the DailyReportCard for today.

    Read-only page. Builds the card using rule-based ranking without LLM.
    """
    return _radar_templates.TemplateResponse(
        "radar_daily_report.html",
        _build_daily_report_page_context(request, report_version=version),
    )


def _build_daily_report_page_context(
    request: Request,
    *,
    daily_report_result: dict | None = None,
    report_version: str | None = None,
) -> dict:
    """Build the shared rule-report and generated-core-report page context."""
    from app.application.radar.daily_report_card import build_daily_report_card
    from app.application.radar.daily_report_store import (
        list_daily_report_versions,
        load_daily_report,
        load_daily_report_version,
    )

    db = next(get_db())
    try:
        card = build_daily_report_card(db)
    finally:
        db.close()

    overview = card.overview
    primary_items = card.primary_items
    secondary_items = card.secondary_items
    date_label = card.date_label
    secondary_all_shown = card.secondary_all_shown
    report_versions = list_daily_report_versions(date_label)
    if daily_report_result is None:
        daily_report_result = (
            load_daily_report_version(date_label, report_version)
            if report_version
            else load_daily_report(date_label)
        )
        if report_version and daily_report_result is None:
            daily_report_result = load_daily_report(date_label)

    return {
        "request": request,
        "date_label": date_label,
        "overview": overview,
        "primary_items": primary_items,
        "secondary_items": secondary_items,
        "secondary_all_shown": secondary_all_shown,
        "safe_external_url": safe_external_url,
        "daily_report_result": daily_report_result,
        "report_versions": report_versions,
        "selected_report_version": (
            daily_report_result.get("version_id")
            if isinstance(daily_report_result, dict)
            else None
        ),
        "DAILY_REPORT_ENABLED": os.getenv("DAILY_REPORT_ENABLED", "").lower() in ("true", "1", "yes"),
    }


def _build_daily_broadcast_page_data(
    report_version: str | None = None,
) -> tuple[object, str, str | None]:
    """Build today's script, preferring the persisted core report."""
    from app.application.radar.daily_broadcast import (
        build_core_report_broadcast_script,
        build_daily_broadcast_script,
    )
    from app.application.radar.daily_report_card import build_daily_report_card
    from app.application.radar.daily_report_store import (
        load_daily_report,
        load_daily_report_version,
    )

    db = next(get_db())
    try:
        card = build_daily_report_card(db)
    finally:
        db.close()

    core_report = (
        load_daily_report_version(card.date_label, report_version)
        if report_version
        else load_daily_report(card.date_label)
    )
    if report_version and core_report is None:
        core_report = load_daily_report(card.date_label)
    if core_report is not None:
        return (
            build_core_report_broadcast_script(core_report),
            "今日核心报告",
            core_report.get("version_id"),
        )

    primary_items = [
        {
            "item_id": item.item_id,
            "source_label": item.source_label,
            "zh_one_liner": item.zh_one_liner,
            "title": item.title,
            "url": item.url,
            "related_directions": item.related_directions,
            "insight_card_id": item.insight_card_id,
        }
        for item in card.primary_items
    ]
    secondary_items = [
        {
            "item_id": item.item_id,
            "source_label": item.source_label,
            "title": item.title,
            "url": item.url,
        }
        for item in card.secondary_items
    ]
    script = build_daily_broadcast_script(
        date_label=card.date_label,
        total_items=card.overview.total_items,
        covered_sources=card.overview.covered_sources,
        with_zh_one_liner=card.overview.with_zh_one_liner,
        with_insight_card=card.overview.with_insight_card,
        primary_items=primary_items,
        secondary_items=secondary_items,
    )
    return script, "今日可读简报", None


def _select_default_daily_audio_job(
    audio_jobs,
    *,
    date_label: str,
    report_version: str | None,
):
    """Select the default playable audio job for today's broadcast page.

    Priority:
    1. generated + same date_label + same report_version
    2. generated + same date_label (list is already sorted by updated_at desc)
    3. None  (don't fall back to yesterday or older)
    """
    from app.application.radar.daily_audio_jobs import select_daily_audio_job

    return select_daily_audio_job(
        audio_jobs,
        date_label=date_label,
        report_version=report_version,
        require_file=False,
    )


@router.get("/daily-report/broadcast", response_class=HTMLResponse)
def get_daily_broadcast(
    request: Request,
    job_id: str | None = Query(None),
    version: str | None = Query(None),
    audio_error: str | None = Query(None),
):
    """Render the DailyBroadcastScript for today.

    Read-only page. Builds the broadcast script from the DailyReportCard without LLM.
    """
    from app.application.radar.daily_audio_jobs import (
        VOICE_OPTIONS,
        is_daily_audio_job_playable,
        list_daily_audio_jobs,
        load_daily_audio_job,
        select_daily_audio_job,
    )
    from app.application.radar.mimo_tts import MiMoTTSSettings, MiMoTTSError

    try:
        settings = MiMoTTSSettings.from_env()
        default_voice = settings.voice
        default_style = settings.style
        tts_config_error = None
    except MiMoTTSError as exc:
        default_voice = os.getenv("MIMO_TTS_VOICE", "冰糖").strip() or "冰糖"
        default_style = os.getenv("MIMO_TTS_STYLE", "").strip()
        tts_config_error = str(exc)
    audio_job = load_daily_audio_job(job_id) if job_id else None
    requested_version = version or (
        audio_job.report_version if audio_job is not None else None
    )
    script, script_basis, report_version = _build_daily_broadcast_page_data(
        requested_version,
    )
    audio_job_is_default = False
    if (
        audio_job is not None
        and audio_job.status == "generated"
        and not is_daily_audio_job_playable(audio_job)
    ):
        audio_error = audio_error or "语音任务记录存在，但音频文件已丢失或损坏，请重新生成。"
        audio_job = None
    if audio_job is None and not job_id:
        # No explicit job_id: auto-select today's latest generated audio
        audio_jobs = list_daily_audio_jobs(limit=20)
        audio_job = select_daily_audio_job(
            audio_jobs,
            date_label=script.date_label,
            report_version=report_version,
        )
        audio_job_is_default = audio_job is not None
    audio_jobs = [
        job
        for job in list_daily_audio_jobs(limit=20)
        if job.status != "generated" or is_daily_audio_job_playable(job)
    ]

    return _radar_templates.TemplateResponse(
        "radar_daily_broadcast.html",
        {
            "request": request,
            "script": script,
            "script_basis": script_basis,
            "report_version": report_version,
            "audio_job": audio_job,
            "audio_jobs": audio_jobs,
            "voice_options": VOICE_OPTIONS,
            "default_voice": default_voice,
            "default_style": default_style,
            "tts_config_error": tts_config_error,
            "audio_error": audio_error,
            "audio_job_is_default": audio_job_is_default,
        },
    )


@router.post("/daily-report/broadcast/audio")
def generate_daily_broadcast_audio(
    background_tasks: BackgroundTasks,
    voice: str = Form("冰糖"),
    style: str = Form(""),
    report_version: str | None = Form(None),
):
    """Queue MiMo TTS audio for today's broadcast script."""
    from app.application.radar.daily_audio_jobs import (
        enqueue_daily_audio_job,
        run_daily_audio_job,
    )
    script, script_basis, report_version = _build_daily_broadcast_page_data(
        report_version,
    )

    try:
        result = enqueue_daily_audio_job(
            script,
            script_basis=script_basis,
            voice=voice,
            style=style,
            report_version=report_version,
        )
    except Exception as exc:
        params = {"audio_error": str(exc)[:300]}
        if report_version:
            params["version"] = report_version
        return RedirectResponse(
            url="/radar/daily-report/broadcast?" + urlencode(params),
            status_code=303,
        )
    if result.should_start:
        background_tasks.add_task(run_daily_audio_job, result.job.job_id)
    return RedirectResponse(
        url="/radar/daily-report/broadcast?"
        + urlencode(
            {
                "job_id": result.job.job_id,
                **({"version": report_version} if report_version else {}),
            }
        ),
        status_code=303,
    )


@router.post("/daily-report/broadcast/audio/{job_id}/resume")
def resume_daily_broadcast_audio(
    job_id: str,
    background_tasks: BackgroundTasks,
):
    """Explicitly resume an interrupted queued or running audio task."""
    from app.application.radar.daily_audio_jobs import (
        resume_daily_audio_job,
        run_daily_audio_job,
    )

    result = resume_daily_audio_job(job_id)
    if result is None:
        return HTMLResponse("语音任务不存在。", status_code=404)
    if result.should_start:
        background_tasks.add_task(run_daily_audio_job, job_id)
    params = {"job_id": job_id}
    if result.job.report_version:
        params["version"] = result.job.report_version
    return RedirectResponse(
        url="/radar/daily-report/broadcast?" + urlencode(params),
        status_code=303,
    )


@router.post("/daily-report/broadcast/audio/{job_id}/retry")
def retry_daily_broadcast_audio(
    job_id: str,
    background_tasks: BackgroundTasks,
):
    from app.application.radar.daily_audio_jobs import (
        retry_daily_audio_job,
        run_daily_audio_job,
    )
    result = retry_daily_audio_job(job_id)
    if result is None:
        return HTMLResponse("语音任务不存在。", status_code=404)
    if result.should_start:
        background_tasks.add_task(run_daily_audio_job, job_id)
    params = {"job_id": job_id}
    if result.job.report_version:
        params["version"] = result.job.report_version
    return RedirectResponse(
        url="/radar/daily-report/broadcast?" + urlencode(params),
        status_code=303,
    )


@router.post("/daily-report/broadcast/audio/{job_id}/delete")
def delete_daily_broadcast_audio(job_id: str):
    from app.application.radar.daily_audio_jobs import delete_daily_audio_job

    if not delete_daily_audio_job(job_id):
        return HTMLResponse("语音任务不存在、正在运行或无法删除。", status_code=409)
    return RedirectResponse(
        url="/radar/daily-report/broadcast",
        status_code=303,
    )


@router.get("/daily-report/broadcast/audio/files/{filename}")
def get_daily_broadcast_audio_file(filename: str):
    """Serve only validated daily broadcast WAV files."""
    from app.application.radar.daily_broadcast import (
        get_daily_broadcast_audio_path,
        is_valid_daily_broadcast_audio_file,
    )

    audio_path = get_daily_broadcast_audio_path(filename)
    if (
        audio_path is None
        or not audio_path.is_file()
        or not is_valid_daily_broadcast_audio_file(audio_path)
    ):
        return HTMLResponse("音频文件不存在。", status_code=404)
    return FileResponse(
        audio_path,
        media_type="audio/wav",
        filename=filename,
        content_disposition_type="inline",
    )


# ── Content-video generation routes (structured content → 9:16 MP4) ──────────

@router.get("/share/{date_label}/video/preflight")
@router.get("/share/today/video/preflight", name="share_today_video_preflight")
async def get_share_video_preflight(request: Request, date_label: str | None = None):
    """Return the result of running content-video preflight checks.

    Used by the share page to show the user what dependencies are available
    before attempting video generation.
    """
    from app.application.content_video.preflight import run_preflight, ContentVideoPreflightResult

    result = run_preflight(require_tts=True)
    items = [
        {
            "name": item.name,
            "ok": item.ok,
            "message": item.message,
            "detail": item.detail,
        }
        for item in result.items
    ]
    return {
        "ok": result.ok,
        "items": items,
    }




def _build_video_source_from_share(db, date_label: str):
    """Build VideoSourceSnapshot from the share page snapshot for a date."""
    from app.application.radar.share_snapshot import build_today_share_snapshot
    from app.application.radar.share_video_adapter import build_video_source_snapshot_from_share_report

    snapshot = build_today_share_snapshot(db, date_label)
    video_snapshot = build_video_source_snapshot_from_share_report(snapshot)
    return video_snapshot


def _resolve_share_tts_provider():
    """Resolve TTS provider for share video generation.

    Rules:
    - DEV_FAKE_TTS=true → FakeTTSProvider (dev only)
    - Otherwise → real MiMo TTS; if not configured → raise TTSProviderError
    """
    import os
    from app.application.radar.mimo_tts import MiMoTTSClient, MiMoTTSError
    from app.application.content_video.audio_renderer import FakeTTSProvider, TTSProviderError

    if os.getenv("DEV_FAKE_TTS", "").strip().lower() == "true":
        return FakeTTSProvider()
    try:
        client = MiMoTTSClient()
        return _MiMoTTSProviderWrapper(client)
    except MiMoTTSError as exc:
        raise TTSProviderError(
            f"TTS provider is not configured: {exc}"
        ) from exc


class _MiMoTTSProviderWrapper:
    """Wraps a MiMoTTSClient to conform to the TTSProvider interface."""

    def __init__(self, client):
        self._client = client

    def synthesize(self, text: str) -> bytes:
        return self._client.synthesize(text)


def _run_content_video_job(request, job_id, input_hash):
    """Background task: resolve TTS and run video generation.

    DB session is NOT passed — request contains only dataclass/pickle-safe data.
    TTS provider is resolved inside this function so it runs in the background context.
    """
    from app.application.content_video.audio_renderer import TTSProviderError
    from app.application.content_video.service import generate_video
    from app.application.content_video.storage import video_storage_for

    try:
        tts_provider = _resolve_share_tts_provider()
    except TTSProviderError as exc:
        # TTS not configured — write failed status using the known input_hash
        storage = video_storage_for(request.source_snapshot.source_key, input_hash)
        storage.write_status(
            job_id=job_id,
            input_hash=input_hash,
            status="failed",
            current_step="generating_scene_audio",
            error=str(exc),
        )
        return

    try:
        generate_video(request, tts_provider=tts_provider, job_id=job_id)
    except Exception:
        # Error is already written to status.json inside generate_video
        pass


def _start_video_generation(db, date_label, force, background_tasks):
    """Shared logic for starting a video generation job (used by today and history routes).

    Returns (job_id, input_hash, immediate_response_dict).
    """
    from fastapi import BackgroundTasks
    from app.application.content_video.models import VideoGenerationRequest
    from app.application.content_video.service import (
        generate_video,
        get_existing_video_status,
    )
    from app.application.content_video.hashing import compute_input_hash
    from app.application.content_video.storage import video_storage_for, ensure_video_dirs
    from app.application.content_video.audio_renderer import TTSProviderError

    video_snapshot = _build_video_source_from_share(db, date_label)
    request = VideoGenerationRequest(source_snapshot=video_snapshot, force=force)
    input_hash = compute_input_hash(request)
    storage = video_storage_for(video_snapshot.source_key, input_hash)
    ensure_video_dirs(storage.base_dir)

    # Check for existing video
    existing = get_existing_video_status(video_snapshot.source_key, input_hash)
    if existing is not None and not force:
        return existing.job_id, input_hash, {
            "job_id": existing.job_id,
            "input_hash": input_hash,
            "status": "existing",
            "current_step": "done",
            "video_path": existing.video_path,
            "poster_path": existing.poster_path,
            "error": None,
        }

    # Run full preflight — fail fast before starting background task
    from app.application.content_video.preflight import run_preflight
    preflight = run_preflight(require_tts=True)
    if not preflight.ok:
        failed_items = [item for item in preflight.items if not item.ok]
        if len(failed_items) == 1:
            error_msg = failed_items[0].message
        else:
            error_lines = "\n".join(f"- {item.message}" for item in failed_items)
            error_msg = f"生成环境检查失败：\n{error_lines}"
        storage.write_status(
            job_id="none",
            input_hash=input_hash,
            status="failed",
            current_step="preflight",
            error=error_msg,
        )
        return "none", input_hash, {
            "job_id": "none",
            "input_hash": input_hash,
            "status": "failed",
            "current_step": "preflight",
            "video_path": None,
            "poster_path": None,
            "error": error_msg,
        }

    # Resolve TTS eagerly here so we fail fast before starting background task
    try:
        tts_provider = _resolve_share_tts_provider()
    except TTSProviderError as exc:
        # TTS not available — write failed status immediately
        storage.write_status(
            job_id="none",
            input_hash=input_hash,
            status="failed",
            current_step="generating_scene_audio",
            error=str(exc),
        )
        return "none", input_hash, {
            "job_id": "none",
            "input_hash": input_hash,
            "status": "failed",
            "current_step": "generating_scene_audio",
            "video_path": None,
            "poster_path": None,
            "error": str(exc),
        }

    # Write initial queued status
    job_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    storage.write_status(
        job_id=job_id,
        input_hash=input_hash,
        status="running",
        current_step="queued",
    )

    # Dispatch background task (only the request dataclass — no DB session)
    background_tasks.add_task(_run_content_video_job, request, job_id, input_hash)

    return job_id, input_hash, {
        "job_id": job_id,
        "input_hash": input_hash,
        "status": "running",
        "current_step": "queued",
        "video_path": None,
        "poster_path": None,
        "error": None,
    }


@router.post("/share/today/video/generate")
def generate_share_today_video(
    background_tasks: BackgroundTasks,
    force: bool = Query(False),
):
    """Trigger structured-content video generation for today's share page.

    Uses BackgroundTasks so the HTTP response returns immediately with job_id.
    Client should poll /share/today/video/status for progress.
    """
    db = next(get_db())
    try:
        job_id, input_hash, payload = _start_video_generation(
            db, None, force, background_tasks
        )
        return payload
    finally:
        db.close()


@router.get("/share/today/video/status")
def get_share_today_video_status(input_hash: str | None = Query(None)):
    """Poll the video generation status for today's share page."""
    from app.application.content_video.models import VideoGenerationRequest
    from app.application.content_video.hashing import compute_input_hash
    from app.application.content_video.storage import video_storage_for

    db = next(get_db())
    try:
        video_snapshot = _build_video_source_from_share(db, None)
        if input_hash is None:
            request = VideoGenerationRequest(source_snapshot=video_snapshot)
            input_hash = compute_input_hash(request)
        storage = video_storage_for(video_snapshot.source_key, input_hash)
        status = storage.read_status()
        if status is None:
            return {"status": "not_found", "input_hash": input_hash}
        return {
            "status": status.get("status"),
            "current_step": status.get("current_step"),
            "video_path": status.get("video_path"),
            "poster_path": status.get("poster_path"),
            "error": status.get("error"),
            "input_hash": status.get("input_hash"),
            "job_id": status.get("job_id"),
            "scene_count": status.get("scene_count"),
            "duration_seconds": status.get("duration_seconds"),
            "file_size_bytes": status.get("file_size_bytes"),
            "tts_mode": status.get("tts_mode"),
        }
    finally:
        db.close()


@router.get("/share/today/video/download")
def download_share_today_video(input_hash: str | None = Query(None)):
    """Download the generated MP4 for today's share page."""
    from app.application.content_video.models import VideoGenerationRequest
    from app.application.content_video.service import get_existing_video_status
    from app.application.content_video.hashing import compute_input_hash

    db = next(get_db())
    try:
        video_snapshot = _build_video_source_from_share(db, None)
        if input_hash is None:
            request = VideoGenerationRequest(source_snapshot=video_snapshot)
            input_hash = compute_input_hash(request)
        existing = get_existing_video_status(video_snapshot.source_key, input_hash)
        if existing is None:
            return HTMLResponse("视频不存在或尚未生成。", status_code=404)
        mp4_path = existing.video_path
        if not mp4_path or not Path(mp4_path).is_file():
            return HTMLResponse("视频文件不存在。", status_code=404)
        date_label = video_snapshot.date_label or "today"
        filename = f"AI_Frontier_Radar_{date_label}.mp4"
        return FileResponse(
            mp4_path,
            media_type="video/mp4",
            filename=filename,
            content_disposition_type="attachment",
        )
    finally:
        db.close()


# ── Historical share video routes ─────────────────────────────────────────────

@router.post("/share/{date_label}/video/generate")
def generate_share_history_video(
    date_label: str,
    background_tasks: BackgroundTasks,
    force: bool = Query(False),
):
    """Trigger structured-content video generation for a historical share page."""
    import re as _re

    if not _re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_label):
        return HTMLResponse("无效日期。", status_code=400)

    db = next(get_db())
    try:
        job_id, input_hash, payload = _start_video_generation(
            db, date_label, force, background_tasks
        )
        return payload
    finally:
        db.close()


@router.get("/share/{date_label}/video/status")
def get_share_history_video_status(date_label: str, input_hash: str | None = Query(None)):
    """Poll the video generation status for a historical share page."""
    import re as _re

    from app.application.content_video.models import VideoGenerationRequest
    from app.application.content_video.hashing import compute_input_hash
    from app.application.content_video.storage import video_storage_for

    if not _re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_label):
        return HTMLResponse("无效日期。", status_code=400)

    db = next(get_db())
    try:
        video_snapshot = _build_video_source_from_share(db, date_label)
        if input_hash is None:
            request = VideoGenerationRequest(source_snapshot=video_snapshot)
            input_hash = compute_input_hash(request)
        storage = video_storage_for(video_snapshot.source_key, input_hash)
        status = storage.read_status()
        if status is None:
            return {"status": "not_found", "input_hash": input_hash}
        return {
            "status": status.get("status"),
            "current_step": status.get("current_step"),
            "video_path": status.get("video_path"),
            "poster_path": status.get("poster_path"),
            "error": status.get("error"),
            "input_hash": status.get("input_hash"),
            "job_id": status.get("job_id"),
            "scene_count": status.get("scene_count"),
            "duration_seconds": status.get("duration_seconds"),
            "file_size_bytes": status.get("file_size_bytes"),
            "tts_mode": status.get("tts_mode"),
        }
    finally:
        db.close()


@router.get("/share/{date_label}/video/download")
def download_share_history_video(date_label: str, input_hash: str | None = Query(None)):
    """Download the generated MP4 for a historical share page."""
    import re as _re

    from app.application.content_video.models import VideoGenerationRequest
    from app.application.content_video.service import get_existing_video_status
    from app.application.content_video.hashing import compute_input_hash

    if not _re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_label):
        return HTMLResponse("无效日期。", status_code=400)

    db = next(get_db())
    try:
        video_snapshot = _build_video_source_from_share(db, date_label)
        if input_hash is None:
            request = VideoGenerationRequest(source_snapshot=video_snapshot)
            input_hash = compute_input_hash(request)
        existing = get_existing_video_status(video_snapshot.source_key, input_hash)
        if existing is None:
            return HTMLResponse("视频不存在或尚未生成。", status_code=404)
        mp4_path = existing.video_path
        if not mp4_path or not Path(mp4_path).is_file():
            return HTMLResponse("视频文件不存在。", status_code=404)
        filename = f"AI_Frontier_Radar_{date_label}.mp4"
        return FileResponse(
            mp4_path,
            media_type="video/mp4",
            filename=filename,
            content_disposition_type="attachment",
        )
    finally:
        db.close()
