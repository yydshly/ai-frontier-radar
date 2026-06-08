"""Project docs hub - white-listed document center."""
from app.project_docs.registry import PROJECT_DOCS_REGISTRY
from app.project_docs.service import ProjectDocsService

__all__ = ["PROJECT_DOCS_REGISTRY", "ProjectDocsService"]
