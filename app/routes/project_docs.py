"""Project Docs Hub routes."""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.context_processors import inject_sources_nav
from app.project_docs.renderer import render_markdown
from app.project_docs.service import ProjectDocsService

router = APIRouter(prefix="/project-docs", tags=["project-docs"])
_docs_service = ProjectDocsService()
_project_docs_templates = Jinja2Templates(
    directory=Path(__file__).resolve().parent.parent / "templates",
    context_processors=[inject_sources_nav],
)


@router.get("/", response_class=HTMLResponse)
def project_docs_index(request: Request):
    """List available project documents by category."""
    categories = _docs_service.list_by_category()
    doc_status = {
        entry.key: _docs_service.get_doc(entry.key).exists
        for entry in _docs_service.list_docs()
    }

    return _project_docs_templates.TemplateResponse(
        "project_docs.html",
        {
            "request": request,
            "categories": categories,
            "doc_status": doc_status,
        },
    )


@router.get("/{doc_key}", response_class=HTMLResponse)
def project_docs_detail(request: Request, doc_key: str):
    """Render a registered project document."""
    doc = _docs_service.get_doc(doc_key)
    if doc.error == "not_found":
        raise HTTPException(status_code=404, detail=f"文档 '{doc_key}' 未在注册表中找到。")

    return _project_docs_templates.TemplateResponse(
        "project_doc_detail.html",
        {
            "request": request,
            "doc": doc,
            "html_content": render_markdown(doc.content or "") if doc.exists else "",
        },
        status_code=200,
    )
