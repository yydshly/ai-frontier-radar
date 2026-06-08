"""Candidate Pool routes - browsing, filtering, and batch operations for candidate items."""
from fastapi import APIRouter, Request, Form, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.application.candidate_pool.services import CandidatePoolService
from app.models import Source

router = APIRouter(prefix="/candidate-pool", tags=["candidate-pool"])


# Status options for the filter dropdown
CANDIDATE_STATUS_OPTIONS = [
    "discovered",
    "ignored",
    "compiling",
    "compiled",
    "failed",
    "manual_required",
]


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


def _truncate_url(url: str | None, max_len: int = 60) -> str:
    """Truncate URL for display."""
    if not url:
        return "-"
    if len(url) <= max_len:
        return url
    return url[:max_len - 3] + "..."


def _get_status_display(status: str) -> str:
    """Get human-readable status display with emoji."""
    status_map = {
        "discovered": "<strong>🆕 待编译</strong>",
        "ignored": "<strong>⏭️ 已忽略</strong>",
        "compiling": "<strong>⚙️ 编译中</strong>",
        "compiled": "<strong>✅ 已编译</strong>",
        "failed": "<strong>❌ 失败</strong>",
        "manual_required": "<strong>👤 需人工</strong>",
    }
    return status_map.get(status, f"<strong>{_escape(status)}</strong>")


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


def _render_candidate_pool_html(
    request: Request,
    items: list,
    total: int,
    page: int,
    page_size: int,
    total_pages: int,
    has_next: bool,
    has_prev: bool,
    sources: list,
    filter_source_key: str | None,
    filter_status: str | None,
    filter_q: str | None,
    flash_message: str | None,
) -> str:
    """Build the candidate pool HTML page."""

    # Build table rows
    rows_html = []
    for item in items:
        url_display = _truncate_url(item.url)
        first_seen = item.first_seen_at.strftime('%Y-%m-%d %H:%M') if item.first_seen_at else '-'
        rows_html.append(f"""<tr>
            <td><input type="checkbox" name="candidate_ids" value="{item.id}"></td>
            <td><a href="/source-items/{item.id}">#{item.id}</a></td>
            <td><code>{_escape(item.source_key)}</code></td>
            <td class="title-cell">{_escape(item.title) if item.title else '无标题'}</td>
            <td class="url-cell"><a href="{_escape(item.url)}" target="_blank" rel="noopener" title="{_escape(item.url)}">{_escape(url_display)}</a></td>
            <td>{_get_status_display(item.status)}</td>
            <td>{first_seen}</td>
            <td><a href="/source-items/{item.id}">详情</a></td>
        </tr>""")

    if not rows_html:
        rows_html.append('<tr><td colspan="8" class="empty-state">暂无候选条目</td></tr>')

    # Pagination HTML
    pagination_html = ""
    if total_pages > 1:
        prev_btn = ""
        if has_prev:
            prev_btn = f'<a href="{_build_pagination_url(request, page - 1, page_size)}" class="btn-secondary">← 上一页</a>'

        next_btn = ""
        if has_next:
            next_btn = f'<a href="{_build_pagination_url(request, page + 1, page_size)}" class="btn-secondary">下一页 →</a>'

        pagination_html = f"""<div class="pagination">
            {prev_btn}
            <span class="pagination-info">第 {page} / {total_pages} 页（共 {total} 条）</span>
            {next_btn}
        </div>"""

    # Source filter options
    source_options = '<option value="">全部</option>'
    for src in sources:
        selected = 'selected' if filter_source_key == src["source_key"] else ''
        source_options += f'<option value="{_escape(src["source_key"])}" {selected}>{_escape(src["source_key"])}</option>'

    # Status filter options
    status_options = '<option value="">全部</option>'
    for s in CANDIDATE_STATUS_OPTIONS:
        selected = 'selected' if filter_status == s else ''
        status_options += f'<option value="{s}" {selected}>{s}</option>'

    # Flash message
    flash_html = ""
    if flash_message:
        flash_html = f'<div class="flash-message">{_escape(flash_message)}</div>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>候选池 Candidate Pool - AI Frontier Radar</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <header>
        <h1>📥 候选池 Candidate Pool</h1>
        <nav>
            <a href="/">← 返回首页</a>
            <a href="/source-items">← 待编译资料</a>
            <a href="/sources">← 信息来源</a>
        </nav>
    </header>

    <main class="wide-page">
        <div class="usage-guide" style="background: linear-gradient(135deg, #e8f5e9 0%, #f1f8e9 100%); border-left: 4px solid #4caf50;">
            <h3>💡 什么是候选池？</h3>
            <p>这里展示已探测但尚未深度编译的资料元数据。你可以从这里批量筛选、忽略不感兴趣的条目，或将优质条目转入编译流程。</p>
        </div>

        {flash_html}

        <div class="filter-bar">
            <form method="get" action="/candidate-pool" class="filter-form">
                <div class="filter-row">
                    <label>
                        来源：
                        <select name="source_key">
                            {source_options}
                        </select>
                    </label>

                    <label>
                        状态：
                        <select name="status">
                            {status_options}
                        </select>
                    </label>

                    <label>
                        搜索：
                        <input type="text" name="q" value="{_escape(filter_q or '')}" placeholder="标题或URL关键词">
                    </label>

                    <button type="submit" class="btn-primary">查询</button>
                    <a href="/candidate-pool" class="btn-secondary">清空筛选</a>
                </div>
            </form>
        </div>

        <div class="batch-actions">
            <form method="post" action="/candidate-pool/batch-ignore" style="display:inline;">
                <button type="submit" class="btn-warning"
                    onclick="return confirm('确定要忽略选中的条目吗？')">批量忽略</button>
            </form>
            <form method="post" action="/candidate-pool/batch-compile" style="display:inline;">
                <button type="submit" class="btn-primary"
                    onclick="return confirm('确定要将选中的条目标记为待编译吗？')">标记为待编译</button>
            </form>
            <small class="muted">（请先勾选要操作的条目）</small>
        </div>

        <p class="result-count">
            共 {total} 条记录，
            当前第 {page}/{total_pages} 页
        </p>

        <div class="table-scroll">
            <table class="source-items-table">
                <thead>
                    <tr>
                        <th>☑</th>
                        <th>ID</th>
                        <th>来源</th>
                        <th>标题</th>
                        <th>URL</th>
                        <th>状态</th>
                        <th>首次发现</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(rows_html)}
                </tbody>
            </table>
        </div>

        {pagination_html}
    </main>

    <footer>
        <p>AI Frontier Radar 候选池</p>
    </footer>
</body>
</html>"""


@router.get("/", response_class=HTMLResponse)
def candidate_pool_page(
    request: Request,
    source_key: str | None = Query(None),
    status: str | None = Query(None),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Display candidate pool with filters and pagination."""
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

        return HTMLResponse(
            _render_candidate_pool_html(
                request=request,
                items=result_page.items,
                total=result_page.total,
                page=result_page.page,
                page_size=result_page.page_size,
                total_pages=result_page.total_pages,
                has_next=result_page.has_next,
                has_prev=result_page.has_prev,
                sources=[{"source_key": s.source_key} for s in sources],
                filter_source_key=source_key,
                filter_status=status,
                filter_q=q,
                flash_message=flash_message,
            ),
            status_code=200,
        )
    finally:
        db.close()


@router.post("/batch-ignore")
def batch_ignore_candidates(candidate_ids: str = Form(...)):
    """Batch ignore selected candidates."""
    from urllib.parse import quote
    db = next(get_db())
    try:
        # Parse comma-separated IDs
        id_list = []
        for part in candidate_ids.split(","):
            part = part.strip()
            if part.isdigit():
                id_list.append(int(part))

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
def batch_compile_candidates(candidate_ids: str = Form(...)):
    """Batch mark candidates for compilation (status = compiling only, no LLM call)."""
    from urllib.parse import quote
    db = next(get_db())
    try:
        # Parse comma-separated IDs
        id_list = []
        for part in candidate_ids.split(","):
            part = part.strip()
            if part.isdigit():
                id_list.append(int(part))

        if id_list:
            service = CandidatePoolService(db)
            result = service.prepare_compile_candidates(id_list)
            message = f"marked {result.updated} for compile"
            if result.skipped > 0:
                message += f", skipped {result.skipped}"
        else:
            message = "no selection"

        response = RedirectResponse(url="/candidate-pool", status_code=303)
        response.set_cookie(key="flash_message", value=message, httponly=True, max_age=60)
        return response
    finally:
        db.close()
