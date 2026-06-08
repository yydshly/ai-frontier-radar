"""SourceItem Compile Service.

Business logic for compiling a SourceItem into an InsightCard.
Migrated from app/main.py POST /source-items/{item_id}/compile route.
"""
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import SourceItem
from app.services.insight_compiler import compile_url
from app.intake import classify_url_by_pattern


@dataclass
class SourceItemCompileResult:
    """Result of a SourceItem compile operation."""
    item_id: int
    ok: bool
    status: str
    insight_card_id: int | None
    message: str | None = None


class SourceItemCompileService:
    """Application service for compiling a SourceItem into an InsightCard.

    Encapsulates the compile business logic so it can be reused by both
    the original /source-items/{id}/compile route and the new
    /candidate-pool/{id}/compile route.
    """

    def __init__(self, db: Session):
        self.db = db

    def compile_item(self, item_id: int) -> SourceItemCompileResult:
        """Compile a SourceItem into an InsightCard.

        Idempotent: if the item is already compiled with a valid insight_card_id,
        returns success without re-calling compile_url.

        Args:
            item_id: The SourceItem ID to compile.

        Returns:
            SourceItemCompileResult with ok=True on success, ok=False on failure.
        """
        item = self.db.query(SourceItem).filter(SourceItem.id == item_id).first()

        # SourceItem not found
        if not item:
            return SourceItemCompileResult(
                item_id=item_id,
                ok=False,
                status="not_found",
                insight_card_id=None,
                message="SourceItem not found",
            )

        # Case A: already compiled — skip re-compilation (idempotent)
        if item.status == "compiled" and item.insight_card_id is not None:
            return SourceItemCompileResult(
                item_id=item_id,
                ok=True,
                status="compiled",
                insight_card_id=item.insight_card_id,
                message="Already compiled (idempotent skip)",
            )

        # Case: empty URL guard
        if not item.url:
            item.status = "failed"
            item.error_message = "SourceItem url is empty"
            item.updated_at = datetime.utcnow()
            try:
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
            return SourceItemCompileResult(
                item_id=item_id,
                ok=False,
                status="failed",
                insight_card_id=None,
                message="SourceItem url is empty",
            )

        # ── Intake classification gate ──────────────────────────────
        decision = classify_url_by_pattern(item.url)

        if not decision.can_compile_directly:
            item.status = "failed"
            item.error_message = f"[intake:blocked] {decision.reason}"
            item.updated_at = datetime.utcnow()
            try:
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
            return SourceItemCompileResult(
                item_id=item_id,
                ok=False,
                status="failed",
                insight_card_id=None,
                message=f"[intake:blocked] {decision.reason}",
            )

        # ── Call compile_url ─────────────────────────────────────────
        try:
            card = compile_url(self.db, item.url)
        except Exception as e:
            item.status = "failed"
            item.error_message = f"Unexpected compile error: {e}"
            item.updated_at = datetime.utcnow()
            try:
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
            return SourceItemCompileResult(
                item_id=item_id,
                ok=False,
                status="failed",
                insight_card_id=None,
                message=f"Unexpected compile error: {e}",
            )

        # Link card regardless of success/failure
        item.insight_card_id = card.id
        item.updated_at = datetime.utcnow()

        if card.status.value == "completed":
            item.status = "compiled"
            item.error_message = None  # Clear old error on success
            result_status = "compiled"
            result_ok = True
            result_message = "Compiled successfully"
        else:
            item.status = "failed"
            item.error_message = card.error_message or "InsightCard compilation failed"
            result_status = "failed"
            result_ok = False
            result_message = card.error_message or "InsightCard compilation failed"

        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        return SourceItemCompileResult(
            item_id=item_id,
            ok=result_ok,
            status=result_status,
            insight_card_id=card.id,
            message=result_message,
        )
