"""Background InsightCard Generation Service.

Provides background compilation for SourceItems using FastAPI BackgroundTasks.
Encapsulates enqueue logic and background execution with proper DB session isolation.
"""
from dataclasses import dataclass
from datetime import datetime

from app.db import SessionLocal
from app.models import SourceItem
from app.application.source_items.compile_service import SourceItemCompileService


@dataclass
class BackgroundCompileEnqueueResult:
    """Result of enqueueing a SourceItem for background compilation."""
    item_id: int
    accepted: bool
    status: str
    message: str


class BackgroundCompileService:
    """Service for enqueueing SourceItems for background InsightCard generation.

    Uses FastAPI BackgroundTasks. Each background task creates its own DB session.

    Idempotency rules:
    - compiled + insight_card_id exists → accepted=False, status="compiled", no-op
    - compiling → accepted=False, status="compiling", no-op
    - discovered / failed / manual_required → accepted=True, status="compiling", enqueued
    """

    def enqueue_item(self, item_id: int) -> BackgroundCompileEnqueueResult:
        """Mark a SourceItem for background compilation.

        Sets status to 'compiling' immediately (before background task runs)
        to provide instant feedback to the user.

        Args:
            item_id: The SourceItem ID to enqueue.

        Returns:
            BackgroundCompileEnqueueResult describing what happened.
        """
        db = SessionLocal()
        try:
            item = db.query(SourceItem).filter(SourceItem.id == item_id).first()

            if not item:
                return BackgroundCompileEnqueueResult(
                    item_id=item_id,
                    accepted=False,
                    status="not_found",
                    message="SourceItem not found",
                )

            # Idempotency: already compiled
            if item.status == "compiled" and item.insight_card_id is not None:
                return BackgroundCompileEnqueueResult(
                    item_id=item_id,
                    accepted=False,
                    status="compiled",
                    message="Already compiled, skipping",
                )

            # Idempotency: already compiling
            if item.status == "compiling":
                return BackgroundCompileEnqueueResult(
                    item_id=item_id,
                    accepted=False,
                    status="compiling",
                    message="Already enqueued for compilation, skipping",
                )

            # Enqueue: discovered, failed, manual_required, or other non-compiled states
            item.status = "compiling"
            item.error_message = None  # Clear old error
            item.updated_at = datetime.utcnow()

            try:
                db.commit()
            except Exception:
                db.rollback()
                raise

            return BackgroundCompileEnqueueResult(
                item_id=item_id,
                accepted=True,
                status="compiling",
                message="Enqueued for background compilation",
            )

        finally:
            db.close()


def run_source_item_compile_in_background(item_id: int) -> None:
    """Background task: compile a SourceItem into an InsightCard.

    Creates its own DB session. Exceptions are caught and written to
    SourceItem.status=failed and SourceItem.error_message.

    This function is designed to be called by FastAPI BackgroundTasks.

    Args:
        item_id: The SourceItem ID to compile.
    """
    db = SessionLocal()
    try:
        service = SourceItemCompileService(db)
        result = service.compile_item(item_id)

        # Result is already committed by compile_item, just log it
        if result.ok:
            # Success - compile_item already set status=compiled
            pass
        else:
            # Failure - compile_item already set status=failed with error_message
            pass

    except Exception as e:
        # Catch any unexpected exception not handled by compile_item
        try:
            item = db.query(SourceItem).filter(SourceItem.id == item_id).first()
            if item:
                item.status = "failed"
                item.error_message = f"Background compile error: {e}"
                item.updated_at = datetime.utcnow()
                db.commit()
        except Exception:
            db.rollback()
            # Re-raise so FastAPI logs the error
            raise
    finally:
        db.close()
