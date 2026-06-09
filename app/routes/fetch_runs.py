"""Fetch Run routes - observability cockpit for source fetch executions."""
from typing import Annotated

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.application.fetch_runs.services import FetchRunService

router = APIRouter(prefix="/fetch-runs", tags=["fetch-runs"])

# Create templates instance for this module (avoids circular import with main.py)
from pathlib import Path
from fastapi.templating import Jinja2Templates
_fetch_runs_templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


# Status display labels
FETCH_RUN_STATUS_LABELS = {
    "pending": "等待中",
    "running": "运行中",
    "success": "成功",
    "partial_failed": "部分失败",
    "failed": "失败",
}


def get_status_display(status: str | None) -> str:
    """Convert FetchRun status to display label."""
    if status is None:
        return "-"
    return FETCH_RUN_STATUS_LABELS.get(status, status)


def _escape(s: str | None) -> str:
    """Escape HTML special characters."""
    if s is None:
        return ""
    return (s
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;"))


def _build_pagination_url(request: Request, page: int, page_size: int) -> str:
    """Build pagination URL with current filters."""
    parts = []
    if request.query_params.get("source_key"):
        parts.append(f"source_key={_escape(request.query_params['source_key'])}")
    if request.query_params.get("status"):
        parts.append(f"status={_escape(request.query_params['status'])}")
    parts.append(f"page={page}")
    parts.append(f"page_size={page_size}")
    return "/fetch-runs?" + "&".join(parts)


@router.get("/", response_class=HTMLResponse)
def fetch_runs_page(
    request: Request,
    source_key: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Display FetchRun list with filters and pagination."""
    db = next(get_db())
    try:
        service = FetchRunService(db)
        result_page = service.list_runs(
            source_key=source_key,
            status=status,
            page=page,
            page_size=page_size,
        )

        # Get all distinct source_keys for the filter dropdown
        from app.models import FetchRun
        from sqlalchemy import func
        source_keys = (
            db.query(FetchRun.source_key, func.count(FetchRun.id))
            .group_by(FetchRun.source_key)
            .order_by(FetchRun.source_key)
            .all()
        )

        return _fetch_runs_templates.TemplateResponse(
            "fetch_runs.html",
            {
                "request": request,
                "runs": result_page.items,
                "total": result_page.total,
                "page": result_page.page,
                "page_size": result_page.page_size,
                "total_pages": result_page.total_pages,
                "has_next": result_page.has_next,
                "has_prev": result_page.has_prev,
                "source_keys": source_keys,
                "filter_source_key": source_key,
                "filter_status": status,
                "get_status_display": get_status_display,
                "build_pagination_url": lambda p, ps: _build_pagination_url(request, p, ps),
            },
        )
    finally:
        db.close()


@router.get("/{run_id}", response_class=HTMLResponse)
def fetch_run_detail_page(request: Request, run_id: int):
    """Display FetchRun detail with related SourceItems (estimated by time window)."""
    db = next(get_db())
    try:
        service = FetchRunService(db)
        detail = service.get_run_detail(run_id)

        if detail is None:
            return RedirectResponse(url="/fetch-runs", status_code=303)

        return _fetch_runs_templates.TemplateResponse(
            "fetch_run_detail.html",
            {
                "request": request,
                "run": detail.run,
                "source": detail.source,
                "related_items": detail.related_items,
                "get_status_display": get_status_display,
            },
        )
    finally:
        db.close()
