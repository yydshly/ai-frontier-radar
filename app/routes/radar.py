"""Radar routes — today's AI frontier reading view.

GET /radar/today renders a catalog + cards + reading-panel layout built
by RadarTodayService. Read-only: no fetching, no compilation, no LLM.
"""
from pathlib import Path

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.db import get_db
from app.context_processors import inject_sources_nav
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

        return _radar_templates.TemplateResponse(
            "radar_today.html",
            {
                "request": request,
                "view": view,
                "display_map": view.display_map,
                "safe_external_url": safe_external_url,
            },
        )
    finally:
        db.close()
