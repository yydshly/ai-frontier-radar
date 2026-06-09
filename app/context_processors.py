"""Jinja2 context processors — injected into all templates."""
from starlette.requests import Request
from app.sources import get_featured_sources


def inject_sources_nav(request: Request):
    """Pass a lightweight source list to all templates for sidebar rendering.

    Calls get_featured_sources() directly; it reads from an in-memory cache
    so this is cheap on every request after the first call.
    """
    try:
        sources = get_featured_sources()
        # Lightweight: only name and source_key for the sidebar
        sources_nav = [
            {"source_key": s.source_key, "name": s.name}
            for s in sources
        ]
    except Exception:
        sources_nav = []
    return {"sources_nav": sources_nav}

