"""Jinja2 context processors — injected into all templates."""
from datetime import datetime
from typing import Any
from starlette.requests import Request
from app.sources import get_featured_sources


def _format_dt(value: Any, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """Safely format a datetime or parseable string. Returns '-' on failure."""
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime(fmt)
    if isinstance(value, str) and value:
        try:
            # Try parsing common formats
            for parse_fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(value[:19], parse_fmt).strftime(fmt)
                except ValueError:
                    continue
            return value  # Return as-is if parsing fails
        except Exception:
            return value
    return str(value)


def inject_sources_nav(request: Request):
    """Pass a lightweight source list to all templates for sidebar rendering.

    Calls get_featured_sources() directly; it reads from an in-memory cache
    so this is cheap on every request after the first call.
    """
    try:
        sources = get_featured_sources()
        # Lightweight: only display name and source_key for the sidebar.
        sources_nav = [
            {
                "source_key": s.get("source_key", ""),
                "name": s.get("display_name") or s.get("name") or s.get("source_key", ""),
            }
            for s in sources
        ][:10]
    except Exception:
        sources_nav = []
    return {"sources_nav": sources_nav}
