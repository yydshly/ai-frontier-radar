"""FastAPI main application."""
import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db, init_db
from app.models import InsightCard, CardStatus, Source, SourceItem, FetchRun, CardDecision, InsightCardBilingualReport
from app.schemas import HealthResponse
from app.sources import sync_sources_config_to_db, get_featured_sources
from app.services.insight_compiler import compile_url
from app.intake import classify_url_by_pattern
from app.application.source_items.compile_service import SourceItemCompileService
from app.application.source_items.background_compile import (
    BackgroundCompileService,
    run_source_item_compile_in_background,
)
from app.card_decisions import ALLOWED_CARD_DECISIONS, is_valid_decision, get_decision_label
from app.logging_config import setup_logging, get_logger
from app.exports.markdown_task import build_action_markdown
from app.exports.markdown_report import build_full_report_markdown
from app.version import APP_VERSION
from app.routes.project_docs import router as project_docs_router
from app.routes.candidate_pool import router as candidate_pool_router
from app.routes.fetch_runs import router as fetch_runs_router


# ── Shared card display helper (V1.0-alpha.8.6) ─────────────────────────────
def _build_card_display_data(card: InsightCard, decision_row: CardDecision | None = None) -> dict:
    """Build display-friendly fields for an InsightCard.

    Handles blocked/failed cards with friendly title fallback, status display,
    and relevance score display. Used by both index and /cards list.
    """
    from urllib.parse import urlparse

    decision_value = decision_row.decision if decision_row else None

    # Determine if this is an intake-blocked card
    is_intake_blocked = (
        card.status == CardStatus.FAILED
        and card.error_message
        and "[intake:blocked]" in card.error_message
    )
    is_failed = card.status == CardStatus.FAILED

    # Compute display title
    if card.source_title:
        display_title = card.source_title
    elif is_intake_blocked:
        parsed = urlparse(card.source_url)
        path = parsed.path if parsed.path else ""
        host_or_path = (parsed.netloc + path) if parsed.netloc else card.source_url
        if len(host_or_path) > 60:
            host_or_path = host_or_path[:57] + "..."
        display_title = f"已拦截：{host_or_path}"
    elif is_failed:
        parsed = urlparse(card.source_url)
        path = parsed.path if parsed.path else ""
        host_or_path = (parsed.netloc + path) if parsed.netloc else card.source_url
        if len(host_or_path) > 60:
            host_or_path = host_or_path[:57] + "..."
        display_title = f"处理失败：{host_or_path}"
    else:
        display_title = card.source_title or "无标题"

    # Compute status display
    if is_intake_blocked:
        status_display = "已拦截"
    elif is_failed:
        status_display = "处理失败"
    else:
        status_display = card.status.value if card.status else "unknown"

    # Relevance score display: "-" for failed/blocked
    relevance_score_display = "-" if (is_intake_blocked or is_failed) else card.relevance_score

    return {
        "display_title": display_title,
        "status_display": status_display,
        "is_intake_blocked": is_intake_blocked,
        "is_failed": is_failed,
        "relevance_score_display": relevance_score_display,
        "decision_value": decision_value,
    }


# Setup
setup_logging()
logger = get_logger(__name__)

# Initialize database on startup
init_db()

# FastAPI app
app = FastAPI(title="AI Frontier Radar", version=APP_VERSION)

# Base directory for templates and static
BASE_DIR = Path(__file__).resolve().parent

# Jinja2 templates
from app.context_processors import inject_sources_nav
templates = Jinja2Templates(directory=BASE_DIR / "templates", context_processors=[inject_sources_nav])

# Static files - mount before any routes
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


# --- Routes ---

@app.get("/health", response_model=HealthResponse)
def health_check():
    """Health check endpoint."""
    return HealthResponse(status="ok")


@app.get("/about", response_class=HTMLResponse)
def about_page(request: Request):
    """System design and technical explanation page.

    V1.0-alpha.8.4: explains the complete processing pipeline, source control,
    URL type classification, failure handling, and LLM analysis boundaries.
    """
    return templates.TemplateResponse("about.html", {"request": request})


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """V0.6: Home page upgraded to personal AI frontier workbench.

    Aggregates dashboard statistics, recent records, and action suggestions
    without calling LLM or network access.
    """
    db = next(get_db())
    try:
        featured_sources = get_featured_sources()

        # ── SourceItem statistics ────────────────────────────────────────────
        source_items_discovered_count = (
            db.query(SourceItem).filter(SourceItem.status == "discovered").count()
        )
        source_items_failed_count = (
            db.query(SourceItem).filter(SourceItem.status == "failed").count()
        )

        # ── Candidate Pool statistics (V1.0-beta.2) ─────────────────────────
        # Candidate pool uses the same SourceItem model with various statuses
        candidate_pool_total_count = db.query(SourceItem).count()
        candidate_pool_discovered_count = (
            db.query(SourceItem).filter(SourceItem.status == "discovered").count()
        )
        candidate_pool_compiling_count = (
            db.query(SourceItem).filter(SourceItem.status == "compiling").count()
        )
        candidate_pool_failed_count = (
            db.query(SourceItem).filter(SourceItem.status == "failed").count()
        )

        # ── InsightCard statistics ──────────────────────────────────────────
        cards_total_count = db.query(InsightCard).count()

        # V1.0-alpha.8.6: unhandled = COMPLETED cards without any CardDecision
        # (excludes failed / blocked cards from unhandled count)
        completed_card_ids = [
            r[0] for r in
            db.query(InsightCard.id).filter(InsightCard.status == CardStatus.COMPLETED).all()
        ]
        if completed_card_ids:
            handled_card_ids = {
                r[0] for r in
                db.query(CardDecision.card_id)
                .filter(CardDecision.card_id.in_(completed_card_ids))
                .distinct()
                .all()
            }
            cards_unhandled_count = len(set(completed_card_ids) - handled_card_ids)
        else:
            cards_unhandled_count = 0

        # Count by decision value
        decision_counts: dict[str, int] = {}
        for decision_value in ALLOWED_CARD_DECISIONS.keys():
            count = (
                db.query(CardDecision)
                .filter(CardDecision.decision == decision_value)
                .count()
            )
            decision_counts[decision_value] = count

        cards_worth_attention_count = decision_counts.get("worth_attention", 0)
        cards_related_to_me_count = decision_counts.get("related_to_me", 0)
        cards_read_later_count = decision_counts.get("read_later", 0)
        cards_ignore_count = decision_counts.get("ignore", 0)
        cards_to_action_count = decision_counts.get("to_action", 0)

        # ── Recent SourceItems (last 5, discovered first) ──────────────────
        recent_source_items = (
            db.query(SourceItem)
            .order_by(SourceItem.last_seen_at.desc())
            .limit(5)
            .all()
        )
        recent_source_items_data = []
        for item in recent_source_items:
            recent_source_items_data.append({
                "id": item.id,
                "source_key": item.source_key,
                "title": item.title or "无标题",
                "url": item.url,
                "status": item.status,
                "insight_card_id": item.insight_card_id,
                "last_seen_at": item.last_seen_at,
            })

        recent_fetch_runs = (
            db.query(FetchRun)
            .order_by(FetchRun.created_at.desc())
            .limit(5)
            .all()
        )
        recent_fetch_runs_data = []
        for run in recent_fetch_runs:
            recent_fetch_runs_data.append({
                "id": run.id,
                "source_key": run.source_key,
                "status": run.status,
                "items_new": run.items_new or 0,
                "items_found": run.items_found or 0,
                "items_updated": run.items_updated or 0,
                "items_failed": run.items_failed or 0,
                "started_at": run.started_at,
                "created_at": run.created_at,
            })

        # ── Recent InsightCards (last 5) ───────────────────────────────────
        recent_cards = (
            db.query(InsightCard)
            .order_by(InsightCard.created_at.desc())
            .limit(5)
            .all()
        )
        recent_card_ids = [c.id for c in recent_cards]
        recent_decisions: dict[int, CardDecision] = {}
        if recent_card_ids:
            decision_rows = (
                db.query(CardDecision)
                .filter(CardDecision.card_id.in_(recent_card_ids))
                .all()
            )
            recent_decisions = {row.card_id: row for row in decision_rows}

        recent_cards_data = []
        for card in recent_cards:
            decision_row = recent_decisions.get(card.id)
            display = _build_card_display_data(card, decision_row)
            decision_value = display["decision_value"]
            decision_note = decision_row.note if decision_row else None

            recent_cards_data.append({
                "id": card.id,
                "source_title": display["display_title"],
                "source_url": card.source_url,
                "status": card.status.value if card.status else "unknown",
                "status_display": display["status_display"],
                "is_intake_blocked": display["is_intake_blocked"],
                "is_failed": display["is_failed"],
                "decision_value": decision_value,
                "decision_label": get_decision_label(decision_value),
                "decision_note": decision_note or "",
                "relevance_score": display["relevance_score_display"],
                "created_at": card.created_at,
            })

        # ── Demo data entry (V1.0-alpha.1) ────────────────────────────────
        demo_source_item = None
        demo_card = None
        demo_source_item_row = (
            db.query(SourceItem)
            .filter(SourceItem.source_key == "demo_ai_frontier")
            .first()
        )
        if demo_source_item_row and demo_source_item_row.insight_card_id:
            demo_card = (
                db.query(InsightCard)
                .filter(InsightCard.id == demo_source_item_row.insight_card_id)
                .first()
            )
            if demo_card and demo_card.status == CardStatus.COMPLETED:
                demo_source_item = demo_source_item_row

        # ── Build context ──────────────────────────────────────────────────
        dashboard_stats = {
            "source_items_discovered": source_items_discovered_count,
            "source_items_failed": source_items_failed_count,
            "cards_total": cards_total_count,
            "cards_unhandled": cards_unhandled_count,
            "cards_worth_attention": cards_worth_attention_count,
            "cards_related_to_me": cards_related_to_me_count,
            "cards_read_later": cards_read_later_count,
            "cards_ignore": cards_ignore_count,
            "cards_to_action": cards_to_action_count,
            # V1.0-beta.2: Candidate Pool statistics
            "candidate_pool_total": candidate_pool_total_count,
            "candidate_pool_discovered": candidate_pool_discovered_count,
            "candidate_pool_compiling": candidate_pool_compiling_count,
            "candidate_pool_failed": candidate_pool_failed_count,
        }

        return templates.TemplateResponse("index.html", {
            "request": request,
            "featured_sources": featured_sources,
            "dashboard_stats": dashboard_stats,
            "recent_fetch_runs": recent_fetch_runs_data,
            "recent_source_items": recent_source_items_data,
            "recent_cards": recent_cards_data,
            "demo_source_item": {
                "id": demo_source_item.id,
                "title": demo_source_item.title or "无标题",
                "url": demo_source_item.url,
                "status": demo_source_item.status,
            } if demo_source_item else None,
            "demo_card": {
                "id": demo_card.id,
                "source_title": demo_card.source_title or "无标题",
                "source_url": demo_card.source_url,
            } if demo_card else None,
        })
    finally:
        db.close()


@app.post("/compile")
def compile_source(url: str = Form(...)):
    """
    Submit a URL for InsightCard compilation.

    Flow:
    1. Validate URL
    2. Classify URL type via intake classifier
    3a. If blocked by strategy: create failed card with reason, redirect to it
    3b. If allowed: proceed with compile_url pipeline
    4. Redirect to card detail page (always, including failed cards)
    """
    logger.info(f"Received compile request for URL: {url}")

    # Basic URL validation
    if not url.startswith(("http://", "https://")):
        return RedirectResponse(url="/", status_code=303)

    # ── Intake classification gate ─────────────────────────────────
    decision = classify_url_by_pattern(url)
    logger.info(f"Intake classification: {decision.page_type.value} | "
                f"strategy={decision.strategy.value} | compile={decision.can_compile_directly}")

    db = next(get_db())
    try:
        # ── Blocked by strategy: create failed card without calling LLM ──
        if not decision.can_compile_directly:
            from app.models import SourceType
            card = InsightCard(
                source_url=url,
                source_type=SourceType.UNKNOWN,
                status=CardStatus.FAILED,
                error_message=f"[intake:blocked] {decision.reason}",
                relevance_score=0,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(card)
            db.commit()
            db.refresh(card)
            logger.info(f"Intake blocked URL {url}: created failed card {card.id}")
            return RedirectResponse(url=f"/cards/{card.id}", status_code=303)

        # ── Allowed: proceed with normal compile pipeline ──
        card = compile_url(db, url)
        return RedirectResponse(url=f"/cards/{card.id}", status_code=303)
    except Exception as e:
        logger.error(f"Unexpected error during compilation: {e}")
        return RedirectResponse(url="/", status_code=303)
    finally:
        db.close()


@app.get("/cards", response_class=HTMLResponse)
def list_cards(request: Request, decision: str | None = None):
    """List InsightCards with optional decision filter.

    V0.4.1: supports ?decision=unhandled | worth_attention | related_to_me |
    read_later | ignore | to_action. Invalid values are treated as "all".
    """
    db = next(get_db())
    try:
        # Normalize filter: 'unhandled' or a known decision value, else empty
        filter_decision = ""
        if decision == "unhandled":
            filter_decision = "unhandled"
        elif decision and is_valid_decision(decision):
            filter_decision = decision
        # else: invalid / empty -> show all (filter_decision stays "")

        cards = (
            db.query(InsightCard)
            .order_by(InsightCard.created_at.desc())
            .all()
        )

        # V0.4.1: load all decisions in one query (avoid N+1)
        card_ids = [card.id for card in cards]
        decision_by_card_id: dict[int, CardDecision] = {}
        if card_ids:
            decision_rows = (
                db.query(CardDecision)
                .filter(CardDecision.card_id.in_(card_ids))
                .all()
            )
            decision_by_card_id = {row.card_id: row for row in decision_rows}

        # Build cards_data and apply Python-level filter
        cards_data = []
        for card in cards:
            decision_row = decision_by_card_id.get(card.id)
            display = _build_card_display_data(card, decision_row)
            decision_value = display["decision_value"]

            # Apply filter
            if filter_decision == "unhandled":
                # V1.0-alpha.8.6.1: only show completed cards without decisions
                if card.status != CardStatus.COMPLETED:
                    continue
                if decision_value is not None:
                    continue
            elif filter_decision and filter_decision != "unhandled":
                if decision_value != filter_decision:
                    continue

            cards_data.append({
                "id": card.id,
                "source_title": display["display_title"],
                "source_url": card.source_url,
                "status": display["status_display"],
                "status_value": card.status.value if card.status else "unknown",
                "relevance_score": display["relevance_score_display"],
                "created_at": card.created_at,
                "decision_value": decision_value,
                "decision_label": get_decision_label(decision_value),
                "is_intake_blocked": display["is_intake_blocked"],
                "is_failed": display["is_failed"],
            })

        # Determine filter label for template display
        filter_decision_label = ""
        if filter_decision == "unhandled":
            filter_decision_label = "未处理"
        elif filter_decision and is_valid_decision(filter_decision):
            filter_decision_label = get_decision_label(filter_decision)

        from app.routes.fetch_runs import safe_external_url

        context = {
            "request": request,
            "cards": cards_data,
            "filter_decision": filter_decision,
            "filter_decision_label": filter_decision_label,
            "decision_options": ALLOWED_CARD_DECISIONS,
            "decision_filter_options": [
                ("unhandled", "未处理"),
                *ALLOWED_CARD_DECISIONS.items(),
            ],
            "total_cards": len(cards),
            "filtered_cards": len(cards_data),
            "safe_external_url": safe_external_url,
        }
        return templates.TemplateResponse("cards.html", context)
    finally:
        db.close()


@app.get("/cards/{card_id}", response_class=HTMLResponse)
def card_detail(request: Request, card_id: int):
    """Show InsightCard detail."""
    db = next(get_db())
    try:
        card = db.query(InsightCard).filter(InsightCard.id == card_id).first()
        if not card:
            return RedirectResponse(url="/cards", status_code=303)

        # V0.4: load user's current decision
        decision_row = (
            db.query(CardDecision)
            .filter(CardDecision.card_id == card.id)
            .first()
        )
        current_decision = decision_row.decision if decision_row else None
        current_note = decision_row.note if decision_row else None

        # V0.8: load bilingual report if exists
        bilingual_report = (
            db.query(InsightCardBilingualReport)
            .filter(InsightCardBilingualReport.card_id == card.id)
            .first()
        )

        # Parse JSON fields for template
        def parse_json_field(value):
            if not value:
                return []
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return []

        # Parse bilingual report JSON fields
        english_key_claims = []
        english_evidence_points = []
        key_terms = []
        if bilingual_report:
            try:
                if bilingual_report.english_key_claims_json:
                    english_key_claims = json.loads(bilingual_report.english_key_claims_json)
            except (json.JSONDecodeError, TypeError):
                english_key_claims = []
            try:
                if bilingual_report.english_evidence_points_json:
                    english_evidence_points = json.loads(bilingual_report.english_evidence_points_json)
            except (json.JSONDecodeError, TypeError):
                english_evidence_points = []
            try:
                if bilingual_report.key_terms_json:
                    key_terms = json.loads(bilingual_report.key_terms_json)
            except (json.JSONDecodeError, TypeError):
                key_terms = []

        # Pass stable string values for template comparisons
        context = {
            "request": request,
            "card": card,
            "status_value": card.status.value if card.status else "unknown",
            "source_type_value": card.source_type.value if card.source_type else "unknown",
            "key_points": parse_json_field(card.key_points_zh),
            "technical_insights": parse_json_field(card.technical_insights_zh),
            "product_opportunities": parse_json_field(card.product_opportunities_zh),
            "risks": parse_json_field(card.risks_zh),
            "action_items": parse_json_field(card.action_items_zh),
            "related_directions": parse_json_field(card.related_user_directions),
            "relevance_reasons": parse_json_field(card.relevance_reasons_zh),
            # V0.4 decision context
            "current_decision": current_decision,
            "current_note": current_note or "",
            "current_decision_label": get_decision_label(current_decision),
            "decision_options": ALLOWED_CARD_DECISIONS,
            # V0.8 bilingual report context
            "bilingual_report": bilingual_report,
            "english_key_claims": english_key_claims,
            "english_evidence_points": english_evidence_points,
            "key_terms": key_terms,
        }
        return templates.TemplateResponse("card_detail.html", context)
    finally:
        db.close()


@app.post("/cards/{card_id}/bilingual-report")
def generate_bilingual_report(card_id: int):
    """Generate or regenerate a bilingual report for an InsightCard.

    V0.8: creates an English core content layer with Chinese explanation
    to help users understand the original material while preserving fidelity.

    If a report already exists, updates it (upsert behavior).
    On failure, does NOT cause 500 - failure info is stored in fidelity_notes_zh.
    """
    from app.services.bilingual_report import (
        build_bilingual_report_prompt,
        upsert_bilingual_report,
        build_mock_bilingual_report,
    )

    db = next(get_db())
    try:
        card = db.query(InsightCard).filter(InsightCard.id == card_id).first()
        if not card:
            return RedirectResponse(url="/cards", status_code=303)

        # Try to read raw text from raw_text_path if available
        source_text = None
        if card.raw_text_path:
            raw_path = Path(card.raw_text_path)
            if raw_path.exists() and raw_path.is_file():
                try:
                    source_text = raw_path.read_text(encoding="utf-8")
                except Exception:
                    pass

        # Fall back to cleaned_text_preview if no raw text
        if not source_text:
            source_text = card.cleaned_text_preview

        # Build prompt
        prompt = build_bilingual_report_prompt(card, source_text)

        # Check if we should use mock mode (no API key or explicit flag)
        use_mock = os.environ.get("MINIMAX_API_KEY") in ("", None)

        if use_mock:
            # Use mock report for testing/development
            report_data = build_mock_bilingual_report(card)
        else:
            # Call LLM for real report
            try:
                from app.llm.factory import create_llm_client

                client = create_llm_client()
                llm_result = client.generate_json(
                    system_prompt="You are a helpful assistant that outputs JSON.",
                    user_prompt=prompt,
                )
                # generate_json returns a dict directly; parse_bilingual_report_response
                # is for raw string responses from call_llm, not needed here.
                report_data = llm_result
            except Exception as e:
                logger.error(f"LLM call failed for bilingual report: {e}")
                # Store error info rather than failing
                report_data = {
                    "english_core_summary": "",
                    "english_key_claims": [],
                    "english_evidence_points": [],
                    "key_terms": [],
                    "chinese_explanation": "",
                    "fidelity_notes_zh": f"[错误] 生成双语报告时发生问题：{e}",
                    "interpretation_boundary_zh": "生成失败，内容仅供参考。",
                    "parse_error": str(e),
                }

        # Upsert the report
        try:
            upsert_bilingual_report(db, card, report_data)
        except Exception as e:
            logger.error(f"Failed to upsert bilingual report: {e}")

        return RedirectResponse(url=f"/cards/{card_id}", status_code=303)
    finally:
        db.close()


@app.post("/cards/{card_id}/decision")
def update_card_decision(card_id: int, decision: str = Form(...), note: str = Form("")):
    """Update (or create) the user's decision for a card.

    One CardDecision per card. Re-submitting updates the existing row.
    Invalid decision values are rejected and redirect back to the detail page
    without writing to the database.
    """
    db = next(get_db())
    try:
        card = db.query(InsightCard).filter(InsightCard.id == card_id).first()
        if not card:
            return RedirectResponse(url="/cards", status_code=303)

        if not is_valid_decision(decision):
            # Invalid decision: don't write, just redirect back to detail
            return RedirectResponse(url=f"/cards/{card_id}", status_code=303)

        # Normalize note: strip whitespace, treat empty as None
        note_clean = (note or "").strip()
        note_value: str | None = note_clean if note_clean else None

        existing = (
            db.query(CardDecision)
            .filter(CardDecision.card_id == card_id)
            .first()
        )

        if existing is None:
            new_decision = CardDecision(
                card_id=card_id,
                decision=decision,
                note=note_value,
            )
            db.add(new_decision)
        else:
            existing.decision = decision
            existing.note = note_value
            # updated_at is auto-updated by onupdate=datetime.utcnow

        db.commit()
        return RedirectResponse(url=f"/cards/{card_id}", status_code=303)
    finally:
        db.close()


@app.post("/cards/{card_id}/delete")
def delete_failed_card(card_id: int):
    """Delete a failed InsightCard and its associated data.

    Only allows deletion of cards with status=FAILED to prevent accidental
    deletion of completed cards. Cleans up CardDecision and
    InsightCardBilingualReport before deleting the InsightCard.
    """
    db = next(get_db())
    try:
        card = db.query(InsightCard).filter(InsightCard.id == card_id).first()
        if not card:
            return RedirectResponse(url="/cards", status_code=303)

        # Only allow deletion of failed cards
        if card.status != CardStatus.FAILED:
            logger.warning(f"Attempted to delete non-failed card {card_id} (status={card.status})")
            return RedirectResponse(url=f"/cards/{card_id}", status_code=303)

        # V1.0-alpha.8.6: clear SourceItem references before deleting card
        # to avoid dangling insight_card_id foreign keys
        db.query(SourceItem).filter(SourceItem.insight_card_id == card_id).update({
            "insight_card_id": None,
            "status": "failed",
            "error_message": "关联的失败记录已删除，可重新处理或忽略",
            "updated_at": datetime.utcnow(),
        })

        # Delete in correct order to handle foreign key constraints
        # 1. CardDecision
        db.query(CardDecision).filter(CardDecision.card_id == card_id).delete()
        # 2. InsightCardBilingualReport
        db.query(InsightCardBilingualReport).filter(InsightCardBilingualReport.card_id == card_id).delete()
        # 3. InsightCard itself
        db.query(InsightCard).filter(InsightCard.id == card_id).delete()

        db.commit()
        logger.info(f"Deleted failed card {card_id}")
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        logger.error(f"Error deleting card {card_id}: {e}")
        db.rollback()
        return RedirectResponse(url=f"/cards/{card_id}", status_code=303)
    finally:
        db.close()


@app.get("/cards/{card_id}/export-markdown", response_class=HTMLResponse)
def card_export_markdown(request: Request, card_id: int):
    """Preview the Markdown task draft for an InsightCard.

    V0.5: renders a full-page preview of the generated Markdown.
    V0.8: includes bilingual report if available.
    Does not modify the database or call LLM.
    """
    db = next(get_db())
    try:
        card = db.query(InsightCard).filter(InsightCard.id == card_id).first()
        if not card:
            return RedirectResponse(url="/cards", status_code=303)

        decision_row = (
            db.query(CardDecision)
            .filter(CardDecision.card_id == card.id)
            .first()
        )

        bilingual_report = (
            db.query(InsightCardBilingualReport)
            .filter(InsightCardBilingualReport.card_id == card.id)
            .first()
        )

        markdown_text = build_action_markdown(card, decision_row, bilingual_report)

        return templates.TemplateResponse("card_export_markdown.html", {
            "request": request,
            "card": card,
            "decision": decision_row,
            "markdown_text": markdown_text,
        })
    finally:
        db.close()


@app.get("/cards/{card_id}/export-markdown/download")
def card_export_markdown_download(card_id: int):
    """Download the Markdown task draft for an InsightCard as a .md file.

    V0.5: streams the file content directly without writing to disk.
    V0.8: includes bilingual report if available.
    """
    db = next(get_db())
    try:
        card = db.query(InsightCard).filter(InsightCard.id == card_id).first()
        if not card:
            return RedirectResponse(url="/cards", status_code=303)

        decision_row = (
            db.query(CardDecision)
            .filter(CardDecision.card_id == card.id)
            .first()
        )

        bilingual_report = (
            db.query(InsightCardBilingualReport)
            .filter(InsightCardBilingualReport.card_id == card.id)
            .first()
        )

        markdown_text = build_action_markdown(card, decision_row, bilingual_report)

        filename = f"insightcard-{card_id}-task.md"
        return PlainTextResponse(
            content=markdown_text,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    finally:
        db.close()


@app.get("/cards/{card_id}/export-report", response_class=HTMLResponse)
def card_export_report_preview(request: Request, card_id: int):
    """Preview the full bilingual markdown report for an InsightCard.

    V0.9: renders a full-page preview of the complete bilingual report.
    V1.0-alpha.8.5: changed to structured HTML reading mode.
    Does not modify the database or call LLM.
    """
    db = next(get_db())
    try:
        card = db.query(InsightCard).filter(InsightCard.id == card_id).first()
        if not card:
            return RedirectResponse(url="/cards", status_code=303)

        decision_row = (
            db.query(CardDecision)
            .filter(CardDecision.card_id == card.id)
            .first()
        )

        bilingual_report = (
            db.query(InsightCardBilingualReport)
            .filter(InsightCardBilingualReport.card_id == card.id)
            .first()
        )

        markdown_text = build_full_report_markdown(card, decision_row, bilingual_report)

        # ── Build structured view data for HTML preview ───────────────────────
        import json as _json

        def _safe_json_list(value):
            if not value:
                return []
            try:
                parsed = _json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except (_json.JSONDecodeError, TypeError):
                return []

        def _safe_json_dict(value):
            if not value:
                return {}
            try:
                parsed = _json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except (_json.JSONDecodeError, TypeError):
                return {}

        # Decision label
        if decision_row:
            from app.card_decisions import get_decision_label
            decision_label = get_decision_label(decision_row.decision)
            decision_note = decision_row.note or ""
        else:
            decision_label = "未处理"
            decision_note = ""

        # Parse bilingual report
        if bilingual_report:
            english_key_claims = _safe_json_list(bilingual_report.english_key_claims_json)
            english_evidence_points = _safe_json_list(bilingual_report.english_evidence_points_json)
            key_terms = _safe_json_list(bilingual_report.key_terms_json)
            fidelity_notes = bilingual_report.fidelity_notes_zh or ""
            interpretation_boundary = bilingual_report.interpretation_boundary_zh or ""
        else:
            english_key_claims = []
            english_evidence_points = []
            key_terms = []
            fidelity_notes = ""
            interpretation_boundary = ""

        # Parse card JSON fields
        key_points = _safe_json_list(card.key_points_zh)
        technical_insights = _safe_json_list(card.technical_insights_zh)
        product_opportunities = _safe_json_list(card.product_opportunities_zh)
        risks = _safe_json_list(card.risks_zh)
        action_items = _safe_json_list(card.action_items_zh)
        relevance_reasons = _safe_json_list(card.relevance_reasons_zh)
        related_directions = _safe_json_list(card.related_user_directions)

        # Source fields
        source_title = card.source_title or "(无标题)"
        source_url = card.source_url or ""
        source_type = card.source_type.value if card.source_type else "unknown"
        source_author = card.source_author or "-"
        source_published_at = card.source_published_at or "-"
        relevance_score = card.relevance_score
        summary_zh = card.summary_zh or "暂无"
        model_name = card.model_name or "-"

        # Has bilingual report flag
        has_bilingual_report = bool(bilingual_report and bilingual_report.english_core_summary)

        return templates.TemplateResponse("card_export_report.html", {
            "request": request,
            "card": card,
            "markdown_text": markdown_text,
            # Structured view data
            "source_title": source_title,
            "source_url": source_url,
            "source_type": source_type,
            "source_author": source_author,
            "source_published_at": source_published_at,
            "relevance_score": relevance_score,
            "model_name": model_name,
            "summary_zh": summary_zh,
            "decision_label": decision_label,
            "decision_note": decision_note,
            # Lists
            "key_points": key_points,
            "technical_insights": technical_insights,
            "product_opportunities": product_opportunities,
            "risks": risks,
            "action_items": action_items,
            "relevance_reasons": relevance_reasons,
            "related_directions": related_directions,
            # Bilingual report
            "has_bilingual_report": has_bilingual_report,
            "english_core_summary": bilingual_report.english_core_summary if bilingual_report else "",
            "english_key_claims": english_key_claims,
            "english_evidence_points": english_evidence_points,
            "key_terms": key_terms,
            "chinese_explanation": bilingual_report.chinese_explanation if bilingual_report else "",
            "fidelity_notes": fidelity_notes,
            "interpretation_boundary": interpretation_boundary,
        })
    finally:
        db.close()


@app.get("/cards/{card_id}/export-report/download")
def card_export_report_download(card_id: int):
    """Download the full bilingual markdown report for an InsightCard as a .md file.

    V0.9: streams the file content directly without writing to disk.
    """
    db = next(get_db())
    try:
        card = db.query(InsightCard).filter(InsightCard.id == card_id).first()
        if not card:
            return RedirectResponse(url="/cards", status_code=303)

        decision_row = (
            db.query(CardDecision)
            .filter(CardDecision.card_id == card.id)
            .first()
        )

        bilingual_report = (
            db.query(InsightCardBilingualReport)
            .filter(InsightCardBilingualReport.card_id == card.id)
            .first()
        )

        markdown_text = build_full_report_markdown(card, decision_row, bilingual_report)

        filename = f"insightcard-{card_id}-report.md"
        return PlainTextResponse(
            content=markdown_text,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    finally:
        db.close()


@app.get("/sources", response_class=HTMLResponse)
def list_sources_page(request: Request):
    """List all configured sources from database."""
    db = next(get_db())
    try:
        # Sync config to DB first (no network access)
        sync_result = sync_sources_config_to_db(db)

        # Query sources from DB, sorted by category then source_key
        sources_orm = (
            db.query(Source)
            .order_by(Source.category, Source.source_key)
            .all()
        )

        # Build FetchRun health map for all source keys
        source_keys = [s.source_key for s in sources_orm]
        from app.application.fetch_runs.services import FetchRunService
        service = FetchRunService(db)
        health_map = service.get_source_health_map(source_keys)

        # Convert to plain dicts for template
        sources_data = []
        for s in sources_orm:
            health = health_map.get(s.source_key)
            sources_data.append({
                "source_key": s.source_key,
                "name": s.name,
                "category": s.category,
                "source_type": s.source_type,
                "fetch_strategy": s.fetch_strategy,
                "enabled": s.enabled,
                "homepage_url": s.homepage_url,
                "feed_url": s.feed_url,
                "fetch_interval_hours": s.fetch_interval_hours,
                "last_checked_at": s.last_checked_at,
                "last_success_at": s.last_success_at,
                "last_error_message": s.last_error_message,
                # V1.0-beta.4: FetchRun health overlay
                "fetch_run_status": health.latest_status if health else None,
                "fetch_run_started_at": health.latest_started_at if health else None,
                "fetch_run_finished_at": health.latest_finished_at if health else None,
                "fetch_run_items_found": health.latest_items_found if health else 0,
                "fetch_run_items_new": health.latest_items_new if health else 0,
                "fetch_run_error_message": health.latest_error_message if health else None,
            })

        return templates.TemplateResponse(
            "sources.html",
            {"request": request, "sources": sources_data, "sync_result": sync_result},
        )
    finally:
        db.close()


@app.post("/sources/{source_key}/fetch")
def trigger_source_fetch(source_key: str):
    """Manually trigger a fetch for the specified source.

    POST only — no GET allowed.

    Creates a FetchRun and redirects to its detail page.
    Returns 404 if source_key does not exist.
    """
    db = next(get_db())
    try:
        from app.application.sources.fetch_service import SourceFetchService
        service = SourceFetchService(db)
        result = service.run_source(source_key)

        if result is None:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=404, content={"detail": f"Source '{source_key}' not found"})

        # Redirect to the FetchRun detail page
        return RedirectResponse(url=f"/fetch-runs/{result.fetch_run.id}", status_code=303)
    finally:
        db.close()


@app.get("/source-items", response_class=HTMLResponse)
def list_source_items_page(
    request: Request,
    source_key: str | None = None,
    status: str | None = None,
    q: str | None = None,
):
    """List discovered SourceItem entries with optional filters."""
    db = next(get_db())
    try:
        # Build query
        query = db.query(SourceItem)

        if source_key:
            query = query.filter(SourceItem.source_key == source_key)

        if status:
            query = query.filter(SourceItem.status == status)

        if q:
            pattern = f"%{q}%"
            query = query.filter(
                (SourceItem.title.ilike(pattern)) | (SourceItem.url.ilike(pattern))
            )

        items_orm = (
            query
            .order_by(SourceItem.last_seen_at.desc(), SourceItem.id.desc())
            .limit(200)
            .all()
        )

        # Get all sources for filter dropdown
        all_sources = db.query(Source).order_by(Source.source_key.asc()).all()

        # Convert to plain dicts
        items_data = []
        for item in items_orm:
            items_data.append({
                "id": item.id,
                "source_key": item.source_key,
                "title": item.title,
                "url": item.url,
                "status": item.status,
                "published_at": item.published_at,
                "first_seen_at": item.first_seen_at,
                "last_seen_at": item.last_seen_at,
                "insight_card_id": item.insight_card_id,
            })

        # Fixed status options
        # Current active states: discovered / compiled / failed.
        # Reserved for future pipeline stages: fetched / skipped_duplicate.
        status_options = [
            "discovered",
            "fetched",
            "compiled",
            "skipped_duplicate",
            "failed",
        ]

        from app.routes.fetch_runs import safe_external_url

        context = {
            "request": request,
            "items": items_data,
            "sources": [{"source_key": s.source_key} for s in all_sources],
            "status_options": status_options,
            "filter_source_key": source_key,
            "filter_status": status,
            "filter_q": q,
            "safe_external_url": safe_external_url,
        }
        return templates.TemplateResponse("source_items.html", context)
    finally:
        db.close()


@app.get("/source-items/{item_id}", response_class=HTMLResponse)
def source_item_detail(request: Request, item_id: int):
    """Show SourceItem detail with optional compile action."""
    db = next(get_db())
    try:
        item = db.query(SourceItem).filter(SourceItem.id == item_id).first()
        if not item:
            return RedirectResponse(url="/source-items", status_code=303)

        # Get associated Source
        source = db.query(Source).filter(Source.id == item.source_id).first()

        # Get associated InsightCard if any
        card = None
        if item.insight_card_id:
            card = db.query(InsightCard).filter(InsightCard.id == item.insight_card_id).first()

        # V1.0-beta.5: compute candidate quality
        from app.application.candidate_quality.services import CandidateQualityService
        quality_service = CandidateQualityService()
        quality = quality_service.evaluate(item)

        # Import safe_external_url helper
        from app.routes.fetch_runs import safe_external_url

        context = {
            "request": request,
            "item": item,
            "source": source,
            "card": card,
            "quality": quality,
            "safe_external_url": safe_external_url,
        }
        return templates.TemplateResponse("source_item_detail.html", context)
    finally:
        db.close()


@app.post("/source-items/{item_id}/compile")
def compile_source_item(item_id: int):
    """Manually compile a SourceItem into an InsightCard (synchronous).

    Idempotent: if the item is already compiled with a valid insight_card_id,
    redirects back without re-calling compile_url.
    """
    db = next(get_db())
    try:
        service = SourceItemCompileService(db)
        result = service.compile_item(item_id)
        return RedirectResponse(url=f"/source-items/{item_id}", status_code=303)
    finally:
        db.close()


@app.post("/source-items/{item_id}/enqueue-compile")
def enqueue_source_item_compile(item_id: int, background_tasks: BackgroundTasks):
    """Enqueue a SourceItem for background InsightCard generation.

    Sets status to 'compiling' immediately, then dispatches a background task
    that calls SourceItemCompileService. Returns immediately (does not wait).

    Idempotent: compiled/composing items are not re-enqueued.
    """
    service = BackgroundCompileService()
    result = service.enqueue_item(item_id)

    if result.accepted:
        background_tasks.add_task(run_source_item_compile_in_background, item_id)
        return RedirectResponse(url=f"/source-items/{item_id}", status_code=303)
    else:
        # Not accepted (already compiled/composing) — just redirect back
        return RedirectResponse(url=f"/source-items/{item_id}", status_code=303)


@app.get("/generation-queue", response_class=HTMLResponse)
def generation_queue_page(request: Request):
    """Display the InsightCard generation queue with items in compiling/compiled/failed states."""
    db = next(get_db())
    try:
        from app.models import SourceItem
        from sqlalchemy import desc
        from app.application.candidates.display import build_candidate_display_card

        # Show items with status in compiling/compiled/failed, ordered by updated_at desc
        items = (
            db.query(SourceItem)
            .filter(SourceItem.status.in_(["compiling", "compiled", "failed", "discovered"]))
            .order_by(desc(SourceItem.updated_at))
            .limit(50)
            .all()
        )

        display_map = {
            item.id: build_candidate_display_card(item)
            for item in items
        }

        from app.routes.fetch_runs import safe_external_url

        return templates.TemplateResponse(
            "generation_queue.html",
            {
                "request": request,
                "items": items,
                "display_map": display_map,
                "safe_external_url": safe_external_url,
            },
        )
    finally:
        db.close()


# ── Mount project docs routes ────────────────────────────────────────────────
app.include_router(project_docs_router)

# ── Mount candidate pool routes ───────────────────────────────────────────────
app.include_router(candidate_pool_router)

# ── Mount fetch runs routes ───────────────────────────────────────────────────
app.include_router(fetch_runs_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
