"""Radar routes — today's AI frontier reading view.

GET /radar/today renders a catalog + cards + reading-panel layout built
by RadarTodayService. Read-only: no fetching, no compilation, no LLM.

POST /radar/today/generate-summaries triggers one-liner generation for
items visible on the current page.
"""
from pathlib import Path

from fastapi import APIRouter, Form, Query, Request
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
from app.models import SourceItem
from app.routes.fetch_runs import safe_external_url

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

        return _radar_templates.TemplateResponse(
            "radar_today.html",
            {
                "request": request,
                "view": view,
                "display_map": view.display_map,
                "safe_external_url": safe_external_url,
                "summary_result": summary_result,
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
