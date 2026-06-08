"""Candidate Pool routes - browsing, filtering, and batch operations for candidate items."""
from typing import Annotated
from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.application.candidate_pool.services import CandidatePoolService
from app.models import Source

router = APIRouter(prefix="/candidate-pool", tags=["candidate-pool"])

# Create templates instance for this module (avoids circular import with main.py)
from pathlib import Path
from fastapi.templating import Jinja2Templates
_candidate_pool_templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


# Status options for the filter dropdown
CANDIDATE_STATUS_OPTIONS = [
    "discovered",
    "ignored",
    "compiling",
    "compiled",
    "failed",
    "manual_required",
]


def is_safe_external_url(url: str | None) -> bool:
    """Check if a URL is a safe external URL (http/https only).

    Rejects:
    - javascript:, data:, vbscript:, file:, blob:, about:
    - Scheme-relative URLs (//evil.com)
    - Empty or None URLs
    - URLs with control characters
    """
    if not url:
        return False

    url = url.strip()

    # Empty after strip
    if not url:
        return False

    # Control characters (except tab, CR, LF which might appear in real URLs)
    if any(c < ' ' and c not in '\t\n\r' for c in url):
        return False

    # Check for dangerous schemes
    dangerous_schemes = (
        'javascript:', 'data:', 'vbscript:', 'file:', 'blob:',
        'about:', 'tel:', 'URN:', 'urn:',
    )
    lower_url = url.lower()
    for scheme in dangerous_schemes:
        if lower_url.startswith(scheme):
            return False

    # Scheme-relative URL
    if url.startswith('//'):
        return False

    # Must start with http:// or https:// (or be a relative path)
    if '/' not in url and ':' in url:
        # Has a scheme but not http/https
        if not lower_url.startswith('http://') and not lower_url.startswith('https://'):
            return False

    return True


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
    if request.query_params.get("q"):
        parts.append(f"q={_escape(request.query_params['q'])}")
    parts.append(f"page={page}")
    parts.append(f"page_size={page_size}")
    return "/candidate-pool?" + "&".join(parts)


@router.get("/", response_class=HTMLResponse)
def candidate_pool_page(
    request: Request,
    source_key: str | None = Query(None),
    status: str | None = Query(None),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Display candidate pool with filters and pagination using Jinja2 template."""
    db = next(get_db())
    try:
        service = CandidatePoolService(db)
        result_page = service.list_candidates(
            source_key=source_key,
            status=status,
            q=q,
            page=page,
            page_size=page_size,
        )

        # Get all sources for filter dropdown
        sources = db.query(Source).order_by(Source.source_key.asc()).all()

        # Check for flash message cookie
        from urllib.parse import unquote
        flash_message = request.cookies.get("flash_message")
        if flash_message:
            flash_message = unquote(flash_message)

        return _candidate_pool_templates.TemplateResponse(
            "candidate_pool.html",
            {
                "request": request,
                "items": result_page.items,
                "total": result_page.total,
                "page": result_page.page,
                "page_size": result_page.page_size,
                "total_pages": result_page.total_pages,
                "has_next": result_page.has_next,
                "has_prev": result_page.has_prev,
                "sources": sources,
                "status_options": CANDIDATE_STATUS_OPTIONS,
                "filter_source_key": source_key,
                "filter_status": status,
                "filter_q": q,
                "flash_message": flash_message,
                "build_pagination_url": lambda p, ps: _build_pagination_url(request, p, ps),
                "safe_external_url": safe_external_url,
            },
        )
    finally:
        db.close()


def _parse_candidate_ids(raw: list[str]) -> list[int]:
    """Parse candidate IDs from form input.

    Handles both comma-separated strings within a list element
    and plain string list elements (from multiple checkbox values).
    """
    if not raw:
        return []

    id_list = []
    for part in raw:
        # Each part might be comma-separated or a single value
        for subpart in part.split(","):
            subpart = subpart.strip()
            if subpart.isdigit():
                id_list.append(int(subpart))
    return id_list


@router.post("/batch-ignore")
def batch_ignore_candidates(request: Request, candidate_ids: Annotated[list[str], Form()] = []):
    """Batch ignore selected candidates."""
    from urllib.parse import quote

    db = next(get_db())
    try:
        id_list = _parse_candidate_ids(candidate_ids)

        if id_list:
            service = CandidatePoolService(db)
            result = service.ignore_candidates(id_list)
            message = f"ignored {result.updated}"
            if result.skipped > 0:
                message += f", skipped {result.skipped}"
        else:
            message = "no selection"

        response = RedirectResponse(url="/candidate-pool", status_code=303)
        response.set_cookie(key="flash_message", value=quote(message), httponly=True, max_age=60)
        return response
    finally:
        db.close()


@router.post("/batch-compile")
def batch_compile_candidates(request: Request, candidate_ids: Annotated[list[str], Form()] = []):
    """Batch mark candidates for compilation (status = compiling only, no LLM call)."""
    from urllib.parse import quote

    db = next(get_db())
    try:
        id_list = _parse_candidate_ids(candidate_ids)

        if id_list:
            service = CandidatePoolService(db)
            result = service.prepare_compile_candidates(id_list)
            message = f"marked {result.updated} for compile"
            if result.skipped > 0:
                message += f", skipped {result.skipped}"
        else:
            message = "no selection"

        response = RedirectResponse(url="/candidate-pool", status_code=303)
        response.set_cookie(key="flash_message", value=quote(message), httponly=True, max_age=60)
        return response
    finally:
        db.close()
