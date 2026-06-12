"""Fetch Run routes - observability cockpit for source fetch executions."""
from fastapi import APIRouter, Request, Query, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db import get_db
from app.application.fetch_runs.services import FetchRunService
from app.application.fetch_runs.delta import FetchDeltaDigestService
from app.application.source_items.background_compile import (
    BackgroundCompileService,
    run_source_item_compile_in_background,
)
from app.context_processors import inject_sources_nav
from app.url_safety import is_safe_external_url as _is_safe_external_url

router = APIRouter(prefix="/fetch-runs", tags=["fetch-runs"])

# Create templates instance for this module (avoids circular import with main.py)
from pathlib import Path
from fastapi.templating import Jinja2Templates
_fetch_runs_templates = Jinja2Templates(
    directory=Path(__file__).resolve().parent.parent / "templates",
    context_processors=[inject_sources_nav],
)


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


# ── Test source identification ─────────────────────────────────────────────────

_TEST_SOURCE_PATTERNS = (
    "test_sync_enq_",
    "test_",
    "orphan_key",
)


def is_test_source_key(source_key: str | None) -> bool:
    """Return True if source_key is a test/source key that should be hidden by default.

    Rules:
    - None/empty → False (real source with no key)
    - "orphan_key" → True
    - starts with "test_sync_enq_" → True
    - starts with "test_" → True
    """
    if not source_key:
        return False
    if source_key == "orphan_key":
        return True
    for pattern in _TEST_SOURCE_PATTERNS:
        if source_key.startswith(pattern):
            return True
    return False


# ── Error display helpers ──────────────────────────────────────────────────────

def get_fetch_run_error_display(run) -> str:
    """Return a human-readable error message for a failed FetchRun.

    Rules:
    - run.error_message has value → return it
    - run.status == 'failed' and no error_message → fallback message
    - run.status == 'partial_failed' and no error_message → partial fallback
    - otherwise → "-"
    """
    if run.error_message:
        return run.error_message
    if run.status == "failed":
        return "失败原因缺失，可能是旧版本运行记录；建议重新运行探测。"
    if run.status == "partial_failed":
        return "部分失败原因缺失，建议查看详情或重新运行探测。"
    return "-"


def get_fetch_run_error_hint(error_message: str | None) -> str | None:
    """Return a human-readable hint for a given error message, or None if no specific hint.

    Rules:
    - contains "HTTP 404" → source URL may be expired
    - contains "Timeout" → source timed out, retry later
    - contains "No candidate article links found" → no articles found, may need rule adjustment
    - contains "unsupported fetch_strategy" → unsupported strategy
    - otherwise → None (no specific hint)
    """
    if not error_message:
        return None
    msg = error_message.lower()
    if "http 404" in msg or "404 not found" in msg:
        return "来源 URL 可能失效，请检查配置中的 homepage_url/feed_url。"
    if "timeout" in msg:
        return "来源响应超时，可稍后重试或增加超时时间。"
    if "no candidate article links found" in msg:
        return "页面可访问，但未识别到文章链接，可能需要调整抓取规则。"
    if "unsupported fetch_strategy" in msg:
        return "当前来源抓取策略不支持，请改为 rss 或 html_index。"
    return None


def is_safe_external_url(url: str | None) -> bool:
    """Return whether a URL is safe to expose or fetch externally."""
    return _is_safe_external_url(url)


def safe_external_url(url: str | None) -> str | None:
    """Return the URL if safe, otherwise None."""
    if is_safe_external_url(url):
        return url
    return None


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
    include_test: int = Query(0, ge=0, le=1),
):
    """Display FetchRun list with filters and pagination."""
    db = next(get_db())
    try:
        exclude_test = not bool(include_test)
        service = FetchRunService(db)
        result_page = service.list_runs(
            source_key=source_key,
            status=status,
            page=page,
            page_size=page_size,
            exclude_test_sources=exclude_test,
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

        # Build the include_test toggle URL
        include_test_url = "/fetch-runs?" + "&".join(
            p for p in [
                f"include_test={1 - include_test}" if include_test else "include_test=1",
                f"source_key={_escape(source_key)}" if source_key else None,
                f"status={_escape(status)}" if status else None,
            ] if p
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
                "show_test_toggle": True,
                "include_test": bool(include_test),
                "include_test_url": include_test_url,
                "get_status_display": get_status_display,
                "get_fetch_run_error_display": get_fetch_run_error_display,
                "get_fetch_run_error_hint": get_fetch_run_error_hint,
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

        # Build delta digest
        digest_service = FetchDeltaDigestService(db)
        digest = digest_service.build_for_run(detail.run)

        # Build run_error_display for failure banner
        run_error_display = None
        if detail.run.status == "failed" and detail.run.error_message:
            msg = detail.run.error_message
            if "unsupported fetch_strategy" in msg.lower():
                run_error_display = {
                    "heading": "探测失败",
                    "reason": msg,
                    "suggestion": "当前来源暂不支持手动探测，请检查 fetch_strategy 是否为 rss 或 html_index。",
                }
            else:
                run_error_display = {
                    "heading": "探测失败",
                    "reason": msg,
                    "suggestion": "请检查来源配置、网络状态，或打开原站确认页面结构。",
                }

        return _fetch_runs_templates.TemplateResponse(
            "fetch_run_detail.html",
            {
                "request": request,
                "run": detail.run,
                "source": detail.source,
                "related_items": detail.related_items,
                "digest": digest,
                "get_status_display": get_status_display,
                "safe_external_url": safe_external_url,
                "run_error_display": run_error_display,
            },
        )
    finally:
        db.close()


@router.post("/{run_id}/source-items/{item_id}/enqueue-compile")
def enqueue_fetch_run_source_item_compile(run_id: int, item_id: int, background_tasks: BackgroundTasks):
    """Enqueue a SourceItem from a FetchRun detail page for background InsightCard generation.

    Sets status to 'compiling' immediately, then dispatches a background task.
    Redirects back to the FetchRun detail page.
    """
    service = BackgroundCompileService()
    result = service.enqueue_item(item_id)

    if result.accepted:
        background_tasks.add_task(run_source_item_compile_in_background, item_id)

    return RedirectResponse(url=f"/fetch-runs/{run_id}", status_code=303)
