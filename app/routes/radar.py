"""Radar routes — today's AI frontier reading view.

GET /radar/today renders a catalog + cards + reading-panel layout built
by RadarTodayService. Read-only: no fetching, no compilation, no LLM.

POST /radar/today/generate-summaries triggers one-liner generation for
items visible on the current page.
"""
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
from urllib.parse import urlencode
import os

from fastapi import APIRouter, BackgroundTasks, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db import get_db
from app.context_processors import inject_sources_nav
from app.application.candidates.one_liner import CandidateOneLinerService, get_one_liner_settings
from app.application.radar.today import (
    RadarTodayService,
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
)
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
    except ValueError:
        return default


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


def _has_zh_one_liner(item: SourceItem) -> bool:
    """Return True if the item already has a Chinese one-liner in raw_metadata_json."""
    import json
    try:
        raw = json.loads(item.raw_metadata_json or "{}")
        return bool(raw.get("zh_one_liner", "").strip())
    except Exception:
        return False


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


@router.get("/today", response_class=HTMLResponse)
def radar_today_page(
    request: Request,
    item_id: int | None = Query(None),
    hours: int = Query(DEFAULT_HOURS, ge=MIN_HOURS, le=MAX_HOURS),
    limit: int = Query(DEFAULT_LIMIT, ge=MIN_LIMIT, le=MAX_LIMIT),
    page: int = Query(1, ge=1),
    per_page: int = Query(DEFAULT_PER_PAGE, ge=MIN_PER_PAGE, le=MAX_PER_PAGE),
    section: str = Query(ALL_KEY),
    summary_success: int | None = Query(None, ge=0),
    summary_skipped: int | None = Query(None, ge=0),
    summary_failed: int | None = Query(None, ge=0),
    summary_details: str | None = Query(None),
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

    summary_result = None
    if (
        summary_success is not None
        or summary_skipped is not None
        or summary_failed is not None
    ):
        summary_result = {
            "success": summary_success or 0,
            "skipped": summary_skipped or 0,
            "failed": summary_failed or 0,
            "details": _parse_summary_details(summary_details),
        }

    update_result = None
    if any(v is not None for v in [
        update_started,
        update_running,
        update_unsupported,
        update_failed,
        update_truncated,
        update_unique_sources,
        update_duplicate_sources,
        update_configured_sources,
        update_filtered_sources,
        update_total,
        update_due,
        update_skipped,
        update_missing,
        update_reason_summary,
        update_plan_source,
    ]):
        update_result = {
            "started": update_started or 0,
            "running": update_running or 0,
            "unsupported": update_unsupported or 0,
            "failed": update_failed or 0,
            "truncated": update_truncated or 0,
            "unique_sources": update_unique_sources or 0,
            "duplicate_sources": update_duplicate_sources or 0,
            "configured_sources": update_configured_sources or 0,
            "filtered_sources": update_filtered_sources or 0,
            # New due-source summary fields (V1.0-beta.1)
            "total": update_total or 0,
            "due": update_due or 0,
            "skipped": update_skipped or 0,
            "missing": update_missing or 0,
            "reason_summary": update_reason_summary or "",
            "reason_summary_label": _humanize_reason_summary(update_reason_summary) or "",
            "plan_source": update_plan_source or "",
        }

    context["summary_result"] = summary_result
    context["update_result"] = update_result
    context["bootstrap_result"] = _build_bootstrap_result(
        dry_run=bootstrap_dry_run,
        total=bootstrap_total,
        eligible=bootstrap_eligible,
        started=bootstrap_started,
        skipped=bootstrap_skipped,
        unsupported=bootstrap_unsupported,
        failed=bootstrap_failed,
        message=bootstrap_message,
        execution_mode=bootstrap_execution_mode,
    )

    return _radar_templates.TemplateResponse(
        "radar_today.html",
        context,
    )


@router.post("/today/daily-report", response_class=HTMLResponse)
def generate_daily_core_report(request: Request):
    """Explicitly generate today's core report (P-003-2).

    POST only — side-effecting (may call the LLM). Gated: the LLM is only
    reached when ``DAILY_REPORT_ENABLED=true``; otherwise the result is
    ``status="disabled"`` and no LLM call happens. Result is rendered inline;
    nothing is persisted.
    """
    from app.db import get_db
    from app.application.radar.daily_report import generate_daily_report

    db = next(get_db())
    try:
        try:
            report = generate_daily_report(db, apply=True)
            daily_report_result = {
                "status": report.status,
                "date_label": report.date_label,
                "input_item_count": report.input_item_count,
                "message": report.message,
                "title": report.title,
                "overview": report.overview,
                "highlights": report.highlights,
            }
        except Exception:
            daily_report_result = {
                "status": "error",
                "message": "今日核心报告生成失败，请稍后重试。",
                "highlights": [],
            }

        context = _build_radar_today_view_context(
            request=request,
            item_id=None,
            hours=DEFAULT_HOURS,
            limit=DEFAULT_LIMIT,
            page=1,
            per_page=DEFAULT_PER_PAGE,
            section=ALL_KEY,
        )
        context["summary_result"] = None
        context["update_result"] = None
        context["daily_report_result"] = daily_report_result
        return _radar_templates.TemplateResponse("radar_today.html", context)
    finally:
        db.close()


def _build_radar_today_view_context(
    request: Request,
    item_id: int | None,
    hours: int,
    limit: int,
    page: int,
    per_page: int,
    section: str,
):
    """Build the context dict for radar today view (shared by full page and panel)."""
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
            "sel": sel,
            "sel_card": sel_card,
        }
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
    )
    return _radar_templates.TemplateResponse(
        "partials/radar_today_panel.html",
        context,
    )


@router.post("/today/items/{item_id}/fetch-content")
def fetch_today_item_content(
    item_id: int,
    section: str = Form(ALL_KEY),
    hours: int = Form(DEFAULT_HOURS),
    limit: int = Form(DEFAULT_LIMIT),
    page: int = Form(1),
    per_page: int = Form(DEFAULT_PER_PAGE),
):
    """Record a safe content-fetch request placeholder for a radar item.

    First version: no network fetch, no LLM, no schema change. It records a
    queued status in raw_metadata_json so the UI can show the chain state.
    """
    db = next(get_db())
    try:
        item = db.query(SourceItem).filter(SourceItem.id == item_id).first()
        if item is not None and item.url:
            try:
                raw = json.loads(item.raw_metadata_json or "{}")
            except (TypeError, json.JSONDecodeError):
                raw = {}
            if not isinstance(raw, dict):
                raw = {}
            raw["content_fetch_status"] = "queued"
            raw["content_fetch_requested_at"] = datetime.utcnow().isoformat()
            raw["content_fetch_note"] = "queued placeholder; no network fetch in V1.0-beta.6"
            item.raw_metadata_json = json.dumps(raw, ensure_ascii=False)
            db.commit()
    finally:
        db.close()

    params = {
        "section": section,
        "item_id": item_id,
        "hours": hours,
        "limit": limit,
        "page": page,
        "per_page": per_page,
    }
    return RedirectResponse(url="/radar/today?" + urlencode(params), status_code=303)


@router.post("/today/generate-summaries")
def generate_today_summaries(
    section: str = Form(ALL_KEY),
    item_id: int | None = Form(None),
    hours: int = Form(DEFAULT_HOURS),
    limit: int = Form(DEFAULT_LIMIT),
    page: int = Form(1),
    per_page: int = Form(DEFAULT_PER_PAGE),
    summary_limit: int = Form(5),
):
    """Generate Chinese summaries for items visible on the current radar page."""
    db = next(get_db())
    try:
        service = RadarTodayService(db)
        view = service.build_today_view(
            selected_item_id=item_id,
            hours=hours,
            limit=limit,
            page=page,
            per_page=per_page,
            section=section,
        )

        # Collect currently-visible items in page display order (deduped).
        visible_items = []
        seen_ids = set()
        for section_view in view.sections:
            for item in section_view.items:
                if item.id not in seen_ids:
                    visible_items.append(item)
                    seen_ids.add(item.id)

        # Re-fetch items to ensure we have session-bound objects, but restore
        # original page-order so visual sequence matches what the user sees.
        visible_ids = [item.id for item in visible_items]
        fetched_items = (
            db.query(SourceItem)
            .filter(SourceItem.id.in_(visible_ids))
            .all()
        )
        items_by_id = {item.id: item for item in fetched_items}
        items = [items_by_id[iid] for iid in visible_ids if iid in items_by_id]

        # Prioritize items that are missing zh_one_liner.
        missing_summary = [item for item in items if not _has_zh_one_liner(item)]
        has_summary = [item for item in items if _has_zh_one_liner(item)]

        max_items = max(1, min(summary_limit, 5))
        items = (missing_summary + has_summary)[:max_items]

        settings = get_one_liner_settings()
        summary_service = CandidateOneLinerService(db, settings=settings)
        results = summary_service.generate_for_items(
            items,
            limit=max_items,
            fill_missing_summary=True,
        )

        success = sum(1 for r in results if r.status == "success")
        skipped = sum(1 for r in results if r.status == "skipped")
        failed = sum(1 for r in results if r.status == "failed")

        # Build per-item detail string (max 5 items, message truncated to avoid long URLs)
        detail_parts = []
        for result in results[:5]:
            item_id = getattr(result, "item_id", None) or ""
            status = getattr(result, "status", "")
            message = getattr(result, "error", "") or ""
            # Sanitize: remove chars that could break URL parsing
            safe_message = message.replace("|", " ").replace(";", " ").replace("\n", " ").strip()
            if len(safe_message) > 80:
                safe_message = safe_message[:77] + "..."
            detail_parts.append(f"{item_id}:{status}:{safe_message}")

        summary_details = ";".join(detail_parts)

        safe_section = view.active_section
        params = {
            "section": safe_section,
            "hours": hours,
            "limit": limit,
            "page": page,
            "per_page": per_page,
            "summary_success": success,
            "summary_skipped": skipped,
            "summary_failed": failed,
        }
        if item_id is not None:
            params["item_id"] = item_id
        if summary_details:
            params["summary_details"] = summary_details
        redirect_url = "/radar/today?" + urlencode(params)
        return RedirectResponse(url=redirect_url, status_code=303)
    finally:
        db.close()


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

    # Build safe section via RadarTodayService
    db = next(get_db())
    try:
        view = RadarTodayService(db).build_today_view(
            selected_item_id=item_id,
            hours=hours,
            limit=limit,
            page=page,
            per_page=per_page,
            section=section,
        )
        safe_section = view.active_section
    finally:
        db.close()

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


@router.get("/daily-report", response_class=HTMLResponse)
def get_daily_report_card(request: Request):
    """Render the DailyReportCard for today.

    Read-only page. Builds the card using rule-based ranking without LLM.
    Accessible via GET; build via POST /radar/daily-report/build.
    """
    from app.application.radar.daily_report_card import build_daily_report_card

    db = next(get_db())
    try:
        card = build_daily_report_card(db)
    finally:
        db.close()

    overview = card.overview
    primary_items = card.primary_items
    secondary_items = card.secondary_items
    date_label = card.date_label

    return _radar_templates.TemplateResponse(
        "radar_daily_report.html",
        {
            "request": request,
            "date_label": date_label,
            "overview": overview,
            "primary_items": primary_items,
            "secondary_items": secondary_items,
        },
    )


@router.post("/daily-report/build")
def build_daily_report_card_action(request: Request):
    """Build today's DailyReportCard and redirect to the report page.

    This is a no-op action that builds the card server-side and redirects
    to GET /radar/daily-report. No LLM is called.
    """
    return RedirectResponse(url="/radar/daily-report", status_code=303)


@router.get("/daily-report/broadcast", response_class=HTMLResponse)
def get_daily_broadcast(request: Request):
    """Render the DailyBroadcastScript for today.

    Read-only page. Builds the broadcast script from the DailyReportCard without LLM.
    """
    from app.application.radar.daily_report_card import build_daily_report_card
    from app.application.radar.daily_broadcast import build_daily_broadcast_script

    db = next(get_db())
    try:
        card = build_daily_report_card(db)
    finally:
        db.close()

    # Convert card items to dicts for the broadcast builder
    primary_items: list[dict] = [
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
    secondary_items: list[dict] = [
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

    return _radar_templates.TemplateResponse(
        "radar_daily_broadcast.html",
        {
            "request": request,
            "script": script,
        },
    )


@router.post("/daily-report/broadcast/audio")
def generate_daily_broadcast_audio(request: Request):
    """Generate TTS audio for today's broadcast script.

    Returns a disabled result if DAILY_BROADCAST_TTS_ENABLED is not set.
    This route does NOT call any external TTS API in V1.0-beta.8.
    """
    from app.application.radar.daily_report_card import build_daily_report_card
    from app.application.radar.daily_broadcast import (
        build_daily_broadcast_script,
        generate_daily_broadcast_audio as _generate_audio,
    )

    db = next(get_db())
    try:
        card = build_daily_report_card(db)
    finally:
        db.close()

    primary_items: list[dict] = [
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
    secondary_items: list[dict] = [
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

    audio_result = _generate_audio(script)

    return _radar_templates.TemplateResponse(
        "radar_daily_broadcast.html",
        {
            "request": request,
            "script": script,
            "audio_result": audio_result,
        },
    )
