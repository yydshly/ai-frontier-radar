"""Project docs service - document access without arbitrary file access."""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.project_docs.registry import PROJECT_DOCS_REGISTRY, DocEntry, is_path_safe, get_doc_path


@dataclass
class DocContent:
    key: str
    title: str
    path: str
    category: str
    description: str
    exists: bool
    content: Optional[str] = None
    error: Optional[str] = None  # "not_found" | "unreadable" | "forbidden"


class ProjectDocsService:
    """Service for accessing white-listed project documents.

    Security model:
    - Only documents registered in PROJECT_DOCS_REGISTRY are accessible
    - Paths are resolved relative to project root, no traversal allowed
    - .env, data/, runtime/, __pycache__/ are never accessible
    - Read errors return DocContent with exists=False, not exceptions
    """

    # Blocked patterns — additional safety net
    _BLOCKED_PATTERNS = (
        ".env",
        "data/",
        "runtime/",
        "__pycache__/",
        ".git/",
        ".venv/",
        ".github/workflows/",
    )

    def list_docs(self) -> list[DocEntry]:
        """Return all registered documents in registration order."""
        return list(PROJECT_DOCS_REGISTRY.values())

    def list_by_category(self) -> dict[str, list[DocEntry]]:
        """Return documents grouped by category, preserving insertion order."""
        result: dict[str, list[DocEntry]] = {}
        for entry in PROJECT_DOCS_REGISTRY.values():
            if entry.category not in result:
                result[entry.category] = []
            result[entry.category].append(entry)
        return result

    def get_doc(self, key: str) -> DocContent:
        """Load a document by its registry key.

        Returns DocContent with exists=False if:
        - key not in registry
        - file not found on disk
        - file unreadable
        - path traversal detected
        """
        entry = PROJECT_DOCS_REGISTRY.get(key)
        if entry is None:
            return DocContent(
                key=key,
                title=key,
                path="",
                category="",
                description="",
                exists=False,
                error="not_found",
            )

        # Check path safety
        if not is_path_safe(entry):
            return DocContent(
                key=entry.key,
                title=entry.title,
                path=entry.path,
                category=entry.category,
                description=entry.description,
                exists=False,
                error="forbidden",
            )

        # Additional blocked pattern check
        path_str = str(get_doc_path(entry)).lower()
        for blocked in self._BLOCKED_PATTERNS:
            if blocked.lower() in path_str:
                return DocContent(
                    key=entry.key,
                    title=entry.title,
                    path=entry.path,
                    category=entry.category,
                    description=entry.description,
                    exists=False,
                    error="forbidden",
                )

        # Check if file exists
        file_path = get_doc_path(entry)
        if not file_path.exists():
            return DocContent(
                key=entry.key,
                title=entry.title,
                path=entry.path,
                category=entry.category,
                description=entry.description,
                exists=False,
                error="not_found",
            )

        # Read content
        try:
            content = file_path.read_text(encoding="utf-8")
            return DocContent(
                key=entry.key,
                title=entry.title,
                path=entry.path,
                category=entry.category,
                description=entry.description,
                exists=True,
                content=content,
            )
        except Exception:
            return DocContent(
                key=entry.key,
                title=entry.title,
                path=entry.path,
                category=entry.category,
                description=entry.description,
                exists=False,
                error="unreadable",
            )

    def doc_exists(self, key: str) -> bool:
        """Check if a document key is registered (does not check disk)."""
        return key in PROJECT_DOCS_REGISTRY
