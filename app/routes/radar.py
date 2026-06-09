"""Radar routes — today's AI frontier reading view.

GET /radar/today renders a catalog + cards + reading-panel layout built
by RadarTodayService. Read-only: no fetching, no compilation, no LLM.

POST /radar/today/generate-summaries triggers one-liner generation for
items visible on the current page.
"""
from pathlib import Path

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


router = APIRouter(prefix="/radar", tags=["radar"])

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
    update_started: int | None = Query(None, ge=0),
    update_running: int | None = Query(None, ge=0),
    update_unsupported: int | None = Query(None, ge=0),
    update_failed: int | None = Query(None, ge=0),
    update_truncated: int | None = Query(None, ge=0),
    update_unique_sources: int | None = Query(None, ge=0),
    update_duplicate_sources: int | None = Query(None, ge=0),
    update_configured_sources: int | None = Query(None, ge=0),
    update_filtered_sources: int | None = Query(None, ge=0),
):
    """Render today's AI frontier radar reading view."""
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

        summary_result = None
        if (
            summary_success is not None
            or summary_skipped is not None
            or summary_failed is not None
        ):
            summary_result = {
                "success": summary_success,
                "skipped": summary_skipped,
                "failed": summary_failed,
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
            }

        return _radar_templates.TemplateResponse(
            "radar_today.html",
            {
                "request": request,
                "view": view,
                "display_map": view.display_map,
                "safe_external_url": safe_external_url,
                "summary_result": summary_result,
                "update_result": update_result,
            },
        )
    finally:
        db.close()


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

        # Collect currently-visible item IDs from all rendered sections.
        visible_ids = []
        seen_ids = set()
        for section_view in view.sections:
            for item in section_view.items:
                if item.id not in seen_ids:
                    visible_ids.append(item.id)
                    seen_ids.add(item.id)

        max_items = max(1, min(summary_limit, 5))
        items = (
            db.query(SourceItem)
            .filter(SourceItem.id.in_(visible_ids))
            .order_by(SourceItem.last_seen_at.desc(), SourceItem.id.desc())
            .all()
        )

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

        safe_section = view.active_section
        redirect_url = (
            f"/radar/today?section={safe_section}"
            f"&hours={hours}&limit={limit}&page={page}&per_page={per_page}"
        )
        if item_id is not None:
            redirect_url += f"&item_id={item_id}"
        redirect_url += (
            f"&summary_success={success}"
            f"&summary_skipped={skipped}"
            f"&summary_failed={failed}"
        )
        return RedirectResponse(url=redirect_url, status_code=303)
    finally:
        db.close()


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
    """Batch-enqueue enabled sources for background fetching.

    Returns to /radar/today with update result stats.
    """
    # Get configured enabled source keys (whitelist for today's radar)
    configured_sources = [s for s in list_sources() if s.enabled]
    configured_keys = {s.source_key for s in configured_sources}
    configured_count = len(configured_keys)

    # Count enabled DB sources not in config for filtered-out stat
    db = next(get_db())
    try:
        db_enabled_keys = {
            row[0] for row in (
                db.query(Source.source_key)
                .filter(Source.enabled == True)  # noqa: E712
                .all()
            )
        }
        filtered_out_count = len(db_enabled_keys - configured_keys)

        # Query DB sources: enabled AND in configured keys, then dedupe
        sources = (
            db.query(Source)
            .filter(Source.enabled == True)  # noqa: E712
            .filter(Source.source_key.in_(configured_keys))
            .order_by(Source.source_key.asc(), Source.id.asc())
            .all()
        )
    finally:
        db.close()

    # Deduplicate by source_key (protects against legacy duplicate rows)
    unique_sources, duplicate_sources = _dedupe_sources_by_key(sources)

    # Separate eligible (supported) vs unsupported sources
    eligible_sources = []
    unsupported = []
    for source in unique_sources:
        if source.fetch_strategy in SUPPORTED_STRATEGIES:
            eligible_sources.append(source)
        else:
            unsupported.append(source)

    # Limit batch size
    max_sources = 30
    truncated_count = max(0, len(eligible_sources) - max_sources)
    eligible_sources = eligible_sources[:max_sources]

    # Enqueue each eligible source
    fetch_service = SourceFetchBackgroundService()
    started = 0
    already_running = 0
    not_found = 0
    failed = 0

    for source in eligible_sources:
        try:
            result = fetch_service.enqueue_source(
                source.source_key,
                background_tasks=background_tasks,
            )
        except Exception:
            failed += 1
            continue

        if result.status == "running" and result.accepted:
            started += 1
        elif result.status == "already_running":
            already_running += 1
        elif result.status == "not_found":
            not_found += 1
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

    # Redirect back to /radar/today with result stats
    redirect_url = (
        f"/radar/today?section={safe_section}"
        f"&hours={hours}&limit={limit}&page={page}&per_page={per_page}"
    )
    if item_id is not None:
        redirect_url += f"&item_id={item_id}"
    redirect_url += (
        f"&update_started={started}"
        f"&update_running={already_running}"
        f"&update_unsupported={len(unsupported)}"
        f"&update_failed={failed}"
        f"&update_truncated={truncated_count}"
        f"&update_unique_sources={len(unique_sources)}"
        f"&update_duplicate_sources={duplicate_sources}"
        f"&update_configured_sources={configured_count}"
        f"&update_filtered_sources={filtered_out_count}"
    )
    return RedirectResponse(url=redirect_url, status_code=303)
