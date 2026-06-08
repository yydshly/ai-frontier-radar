"""Project Docs Hub routes."""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse

from app.project_docs.service import ProjectDocsService
from app.project_docs.renderer import render_markdown

router = APIRouter(prefix="/project-docs", tags=["project-docs"])
_docs_service = ProjectDocsService()


@router.get("/", response_class=HTMLResponse)
def project_docs_index(request: Request):
    """Project Docs Hub — list all available documents by category."""
    categories = _docs_service.list_by_category()

    # Check which docs actually exist on disk
    doc_status: dict[str, bool] = {}
    for key in _docs_service.list_docs():
        doc = _docs_service.get_doc(key.key)
        doc_status[key.key] = doc.exists

    return HTMLResponse(
        _build_index_html(categories, doc_status, request),
        status_code=200,
    )


@router.get("/{doc_key}", response_class=HTMLResponse)
def project_docs_detail(request: Request, doc_key: str):
    """View a specific document by its registry key.

    Returns 404 if the key is not in the registry.
    Returns a friendly 'not found' page if the file is not on disk.
    """
    doc = _docs_service.get_doc(doc_key)

    if doc.error == "not_found":
        raise HTTPException(status_code=404, detail=f"文档 '{doc_key}' 未在注册表中找到。")

    return HTMLResponse(
        _build_detail_html(doc, request),
        status_code=200 if doc.exists else 200,  # 200 even if not found (friendly message)
    )


# ── HTML builders ──────────────────────────────────────────────────────────────

def _build_index_html(categories: dict[str, list], doc_status: dict[str, bool], request: Request) -> str:
    """Build the project docs index page HTML."""
    body_parts = [
        "<!DOCTYPE html>",
        "<html lang='zh-CN'>",
        "<head>",
        "<meta charset='UTF-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>",
        "<title>项目资料中心 - AI Frontier Radar</title>",
        "<link rel='stylesheet' href='/static/style.css'>",
        "</head>",
        "<body>",
        "<header>",
        "<h1>📚 项目资料中心</h1>",
        "<nav><a href='/'>← 返回首页</a> | <a href='/about'>关于系统</a></nav>",
        "</header>",
        "<main>",
        "<p class='lead'>这里是 AI Frontier Radar 的项目资料中心，收录项目定位、架构设计、技术路线、运行验收和 Beta 规划等文档。</p>",
    ]

    for category, entries in categories.items():
        body_parts.append(f"<section class='doc-category'>")
        body_parts.append(f"<h2>{category}</h2>")
        body_parts.append("<ul class='doc-list'>")
        for entry in entries:
            status = doc_status.get(entry.key, False)
            status_label = "✅ 可用" if status else "⏳ 待补充"
            status_class = "doc-available" if status else "doc-pending"
            body_parts.append(
                f"<li class='{status_class}'>"
                f"<a href='/project-docs/{entry.key}' class='doc-title'>{entry.title}</a>"
                f"<span class='doc-status'>{status_label}</span>"
                f"<p class='doc-desc'>{entry.description}</p>"
                f"<p class='doc-path'><code>{entry.path}</code></p>"
                f"</li>"
            )
        body_parts.append("</ul>")
        body_parts.append("</section>")

    body_parts.extend([
        "</main>",
        "<footer><p>AI Frontier Radar - 项目资料中心</p></footer>",
        "</body>",
        "</html>",
    ])
    return "\n".join(body_parts)


def _build_detail_html(doc, request) -> str:
    """Build the project docs detail page HTML."""
    if not doc.exists:
        body_parts = [
            "<!DOCTYPE html>",
            "<html lang='zh-CN'>",
            "<head>",
            "<meta charset='UTF-8'>",
            "<meta name='viewport' content='width=device-width, initial-scale=1.0'>",
            "<title>文档未找到 - 项目资料中心</title>",
            "<link rel='stylesheet' href='/static/style.css'>",
            "</head>",
            "<body>",
            "<header>",
            "<h1>📚 项目资料中心</h1>",
            "<nav><a href='/'>← 返回首页</a> | <a href='/project-docs'>← 返回资料中心</a></nav>",
            "</header>",
            "<main>",
            "<div class='error-banner'>",
            f"<h2>文档未创建 / 待补充</h2>",
            f"<p>文档「{doc.title}」（<code>{doc.path}</code>）尚未创建或无法读取。</p>",
            "<p>请等待后续补充，或在 GitHub 仓库中提交该文档。</p>",
            "</div>",
            "</main>",
            "</body>",
            "</html>",
        ]
        return "\n".join(body_parts)

    # Render markdown
    html_content = render_markdown(doc.content or "")

    body_parts = [
        "<!DOCTYPE html>",
        "<html lang='zh-CN'>",
        "<head>",
        "<meta charset='UTF-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>",
        f"<title>{doc.title} - 项目资料中心</title>",
        "<link rel='stylesheet' href='/static/style.css'>",
        "<style>",
        # Minimal styles for doc reading
        ".doc-content { max-width: 800px; margin: 0 auto; line-height: 1.7; }",
        ".doc-content h1 { font-size: 1.6em; border-bottom: 2px solid #ddd; padding-bottom: 0.3em; }",
        ".doc-content h2 { font-size: 1.3em; border-bottom: 1px solid #eee; padding-bottom: 0.2em; margin-top: 1.5em; }",
        ".doc-content h3 { font-size: 1.1em; margin-top: 1.2em; }",
        ".doc-content p { margin: 0.8em 0; }",
        ".doc-content ul, .doc-content ol { margin: 0.8em 0; padding-left: 2em; }",
        ".doc-content li { margin: 0.3em 0; }",
        ".doc-content blockquote { border-left: 4px solid #ccc; margin: 1em 0; padding: 0.5em 1em; color: #555; background: #f9f9f9; }",
        ".doc-content code { background: #f4f4f4; padding: 0.15em 0.4em; border-radius: 3px; font-size: 0.9em; }",
        ".doc-content pre { background: #f4f4f4; padding: 1em; border-radius: 4px; overflow-x: auto; }",
        ".doc-content pre code { background: none; padding: 0; }",
        ".doc-content a { color: #1976d2; }",
        ".doc-content hr { border: none; border-top: 1px solid #ddd; margin: 1.5em 0; }",
        ".doc-content strong { font-weight: 600; }",
        ".doc-meta { background: #f5f5f5; padding: 0.8em 1em; border-radius: 4px; margin-bottom: 1.5em; }",
        ".doc-meta .doc-meta-title { font-size: 1.2em; font-weight: 600; }",
        ".doc-meta .doc-meta-category { color: #666; font-size: 0.9em; }",
        ".doc-meta .doc-meta-path { color: #888; font-size: 0.85em; }",
        ".back-link { margin: 1em 0; }",
        ".back-link a { color: #1976d2; text-decoration: none; }",
        ".back-link a:hover { text-decoration: underline; }",
        "</style>",
        "</head>",
        "<body>",
        "<header>",
        "<h1>📚 项目资料中心</h1>",
        "<nav><a href='/'>← 返回首页</a> | <a href='/project-docs'>← 返回资料中心</a> | <a href='/about'>关于系统</a></nav>",
        "</header>",
        "<main>",
        "<div class='doc-content'>",
        f"<div class='back-link'><a href='/project-docs'>← 返回资料中心</a></div>",
        "<div class='doc-meta'>",
        f"<div class='doc-meta-title'>{doc.title}</div>",
        f"<div class='doc-meta-category'>分类：{doc.category}</div>",
        f"<div class='doc-meta-path'><code>{doc.path}</code></div>",
        "</div>",
        html_content,
        "</div>",
        "</main>",
        "<footer><p>AI Frontier Radar - 项目资料中心</p></footer>",
        "</body>",
        "</html>",
    ]
    return "\n".join(body_parts)
